#!/usr/bin/env python3
"""JPEG encoder for the live video stream.

Runs as its own process so none of this lands in the render loop. Reads frames
the video engine drops in /dev/shm and writes JPEGs back for the web server to
hand out as motion jpeg.

Normally the engine passes its mode surface through untouched and the scaling
happens here, on another core:

    python3 stream_encoder.py --width 640 --height 360 --fps 30 \\
        --src-bits 32 --src-masks 16711680,65280,255,0 --smooth

Without --src-bits the engine is scaling before it publishes and the payload
is already packed RGB at the target size.

pygame does not expose the JPEG quality setting, so bandwidth is dialled in
with the frame size and rate instead.
"""

import argparse
import ctypes
import io
import os
import signal
import sys
import time

# no display needed, this process only touches surfaces in memory
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

import framebus

# generous, a 960x540 jpeg is well under a hundred kilobytes
JPEG_CAPACITY = 512 * 1024

# pygame renamed these in 2.1.3, the device may be running either
_frombytes = getattr(pygame.image, "frombytes", None) or pygame.image.fromstring


def die_with_parent():
    """Ask the kernel to kill us when the engine goes.

    Set here, in the child, once it is a program of its own and single
    threaded again. A preexec_fn in the parent runs between fork and exec,
    which Python's documentation calls unsafe from a multi-threaded process:
    locks held by threads that do not exist in the child come across held,
    and the dlopen this needs wants one. The engine has threads.
    """
    try:
        PR_SET_PDEATHSIG = 1
        ctypes.CDLL("libc.so.6").prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
    except Exception:
        pass

    # the signal only fires from here on, so a parent that went while we were
    # starting would never send it
    if os.getppid() == 1:
        os._exit(0)


class Encoder:
    """Turns one published frame into one JPEG, reusing everything it can.

    Nothing here may allocate per frame. The encoder grew about eight
    megabytes a minute on the instrument with the stream running, and on a
    gigabyte machine with swap disabled that ends as a freeze that needs the
    plug pulled. A scale() with no destination returns a new surface every
    call, which at fifteen a second is what this avoids.

    Only bytes go to pygame. A memoryview onto the shared mapping would save
    the copy, but BufferProxy.write refuses one -- "argument 1 must be a
    read-only bytes-like object, not memoryview" -- once a frame, forever.
    """

    def __init__(self, out_size, src_bits, masks, smooth=False):
        self.out_size = out_size
        self.src_bits = src_bits
        self.masks = masks
        self.passthrough = src_bits > 0
        self.scaler = pygame.transform.smoothscale if smooth \
            else pygame.transform.scale

        self.src_surface = None
        self.src_size = None
        self.out_surface = None
        self.buf = io.BytesIO()

        # pygame grew the destination argument to scale() in 2.0, and which
        # build the instrument has is not known here. The first frame finds
        # out, once, rather than raising into the caller every frame
        self.scale_into = True

    def _size_for(self, width, height):
        self.src_size = (width, height)
        self.src_surface = pygame.Surface(self.src_size, 0, self.src_bits,
                                          self.masks)
        # the same format as the source, which is what scaling into a surface
        # you already have requires
        self.out_surface = pygame.Surface(self.out_size, 0, self.src_bits,
                                          self.masks)
        print(f"source is {width}x{height}", flush=True)

    def _scaled(self, source):
        if self.scale_into:
            try:
                self.scaler(source, self.out_size, self.out_surface)
                return self.out_surface
            except (TypeError, ValueError, pygame.error):
                self.scale_into = False
                print("pygame will not scale into a surface,"
                      " allocating one a frame", flush=True)
        return self.scaler(source, self.out_size)

    def frame(self, payload, width, height):
        """The JPEG for one published frame, or None to skip it."""
        if self.passthrough:
            if self.src_size != (width, height):
                self._size_for(width, height)
            # identical masks and depth, so this is a straight copy in
            self.src_surface.get_view('0').write(payload)
            surface = self._scaled(self.src_surface)
        else:
            if len(payload) != width * height * 3:
                return None
            surface = _frombytes(payload, (width, height), "RGB")

        self.buf.seek(0)
        self.buf.truncate(0)
        pygame.image.save(surface, self.buf, "frame.jpg")
        # getvalue, not getbuffer: an outstanding buffer export would refuse
        # the truncate on the next frame
        return self.buf.getvalue()


def main():
    die_with_parent()

    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--src-bits", type=int, default=0,
                    help="bit depth of the surface the engine passes through")
    ap.add_argument("--src-masks", default="",
                    help="comma separated r,g,b,a masks of that surface")
    ap.add_argument("--smooth", action="store_true",
                    help="average pixels when scaling instead of dropping them")
    args = ap.parse_args()

    pygame.init()

    out_size = (args.width, args.height)
    masks = tuple(int(m) for m in args.src_masks.split(",")) if args.src_masks \
        else (0, 0, 0, 0)
    encoder = Encoder(out_size, args.src_bits, masks, args.smooth)

    # the engine creates the raw bus, wait for it to show up. its capacity has
    # to match what the engine allocated, so read it from the file itself
    raw = None
    while raw is None:
        try:
            size = os.path.getsize(framebus.RAW_PATH)
            raw = framebus.FrameBus(framebus.RAW_PATH,
                                    (size - framebus.HEADER) // 2)
        except (OSError, ValueError, ZeroDivisionError):
            time.sleep(0.5)

    out = framebus.FrameBus(framebus.JPEG_PATH, JPEG_CAPACITY, create=True)
    print(f"stream encoder up: {args.width}x{args.height} {args.fps}fps"
          f"{' passthrough' if args.src_bits > 0 else ''}"
          f"{' smoothed' if args.smooth else ''}", flush=True)

    # the engine already publishes at the requested rate, so encode every
    # frame it offers rather than rate limiting a second time here, which
    # only ever drops frames and makes the result stutter
    idle = 1.0 / max(1.0, args.fps) / 8

    last_seq = 0
    while True:
        frame = raw.read()
        if frame is None or frame[3] == last_seq:
            time.sleep(idle)
            continue

        payload, width, height, last_seq = frame

        try:
            jpeg = encoder.frame(payload, width, height)
            if jpeg is not None:
                out.publish(jpeg, out_size[0], out_size[1])
        except Exception as e:
            print(f"encode failed: {e}", flush=True)
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
