#!/usr/bin/env python3
"""JPEG encoder for the live video stream.

Runs as its own process so the encode never lands in the render loop. Reads raw
RGB frames the video engine drops in /dev/shm and writes JPEGs back for the web
server to hand out as motion jpeg.

    python3 stream_encoder.py --width 480 --height 270 --fps 12

pygame does not expose the jpeg quality setting, so bandwidth is dialled in
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

# generous, a 480x270 jpeg is a few tens of kilobytes
JPEG_CAPACITY = 512 * 1024

# pygame renamed these in 2.1.3, the device may be running either
_frombytes = getattr(pygame.image, "frombytes", None) or pygame.image.fromstring


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    ap.add_argument("--fps", type=float, default=12.0)
    args = ap.parse_args()

    pygame.init()

    raw_capacity = args.width * args.height * 3
    interval = 1.0 / max(1.0, args.fps)

    # the engine creates the raw bus, wait for it to show up
    raw = None
    while raw is None:
        try:
            raw = framebus.FrameBus(framebus.RAW_PATH, raw_capacity)
        except (OSError, ValueError):
            time.sleep(0.5)

    out = framebus.FrameBus(framebus.JPEG_PATH, JPEG_CAPACITY, create=True)
    print(f"stream encoder up: {args.width}x{args.height} "
          f"{args.fps}fps", flush=True)

    last_seq = 0
    while True:
        frame = raw.read()
        if frame is None or frame[3] == last_seq:
            time.sleep(interval / 4)
            continue

        payload, width, height, last_seq = frame
        if len(payload) != width * height * 3:
            continue

        try:
            surface = _frombytes(payload, (width, height), "RGB")
            buf = io.BytesIO()
            pygame.image.save(surface, buf, "frame.jpg")
            out.publish(buf.getvalue(), width, height)
        except Exception as e:
            print(f"encode failed: {e}", flush=True)
            time.sleep(1)

        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
