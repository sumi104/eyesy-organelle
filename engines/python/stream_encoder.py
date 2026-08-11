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
import io
import os
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


def main():
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
    passthrough = args.src_bits > 0
    masks = tuple(int(m) for m in args.src_masks.split(",")) if args.src_masks \
        else (0, 0, 0, 0)
    scaler = pygame.transform.smoothscale if args.smooth \
        else pygame.transform.scale

    # sized once the first frame says how big the source is
    src_surface = None
    src_size = None

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
          f"{' passthrough' if passthrough else ''}"
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
            if passthrough:
                if src_size != (width, height):
                    src_size = (width, height)
                    src_surface = pygame.Surface(src_size, 0, args.src_bits,
                                                 masks)
                    print(f"source is {width}x{height}", flush=True)
                # identical masks and depth, so this is a straight copy in
                src_surface.get_view('0').write(payload)
                surface = scaler(src_surface, out_size)
            else:
                if len(payload) != width * height * 3:
                    continue
                surface = _frombytes(payload, (width, height), "RGB")

            buf = io.BytesIO()
            pygame.image.save(surface, buf, "frame.jpg")
            out.publish(buf.getvalue(), out_size[0], out_size[1])
        except Exception as e:
            print(f"encode failed: {e}", flush=True)
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
