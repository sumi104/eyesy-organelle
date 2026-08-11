#!/usr/bin/env python3
"""Turn raw 128x64 SSD1306 frame buffer dumps into a PNG contact sheet.

Works on the dumps written by oled_preview, and on anything else that captures
the 1024 byte pix_buf. Standard library only, so it runs anywhere.

    python3 oled_view.py /tmp/oled*.raw -o /tmp/oled.png
"""

import argparse
import struct
import sys
import zlib

WIDTH = 128
HEIGHT = 64


def unpack(buf):
    """SSD1306 page format -> list of rows of 0/1."""
    rows = [[0] * WIDTH for _ in range(HEIGHT)]
    for page in range(HEIGHT // 8):
        for column in range(WIDTH):
            byte = buf[(page * WIDTH) + column]
            for bit in range(8):
                rows[(page * 8) + bit][column] = (byte >> bit) & 1
    return rows


def write_png(path, pixels, width, height):
    """Grayscale PNG, no dependencies."""
    raw = bytearray()
    for row in pixels:
        raw.append(0)  # filter type none
        raw.extend(row)

    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        return out + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", header)
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="raw 1024 byte frame buffer dumps")
    ap.add_argument("-o", "--out", default="oled.png")
    ap.add_argument("-s", "--scale", type=int, default=3)
    ap.add_argument("--gap", type=int, default=6, help="pixels between frames")
    args = ap.parse_args()

    frames = []
    for path in args.files:
        with open(path, "rb") as f:
            buf = f.read()
        if len(buf) != 1024:
            sys.exit(f"{path}: expected 1024 bytes, got {len(buf)}")
        frames.append(unpack(buf))

    scale = args.scale
    fw, fh = WIDTH * scale, HEIGHT * scale
    gap = args.gap
    sheet_w = fw + (gap * 2)
    sheet_h = (fh + gap) * len(frames) + gap

    # 40 is the dark surround, 0 off pixel, 255 lit pixel
    sheet = [[40] * sheet_w for _ in range(sheet_h)]

    for index, frame in enumerate(frames):
        top = gap + (index * (fh + gap))
        for y in range(fh):
            row = frame[y // scale]
            out = sheet[top + y]
            for x in range(fw):
                out[gap + x] = 255 if row[x // scale] else 0

    write_png(args.out, sheet, sheet_w, sheet_h)
    print(f"wrote {args.out} ({sheet_w}x{sheet_h}, {len(frames)} frames)")


if __name__ == "__main__":
    main()
