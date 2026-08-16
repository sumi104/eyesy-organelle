#!/usr/bin/env python3
"""Turn raw 128x64 SSD1306 frame buffer dumps into a PNG contact sheet.

Works on the dumps written by oled_preview, and on anything else that captures
the 1024 byte pix_buf. Standard library only, so it runs anywhere.

    python3 oled_view.py /tmp/oled*.raw -o /tmp/oled.png

--html plays the frames instead of stacking them, at the interval the display
actually refreshes on, which is the only way to judge the speed of anything
that moves without flashing the device. Pair it with oled_anim.

    python3 oled_view.py --html /tmp/anim.html /tmp/anim*.raw
"""

import argparse
import base64
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


def png_bytes(pixels, width, height):
    """The same PNG, in memory, for embedding."""
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        raw.extend(row)

    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        return out + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


HTML = """<!doctype html>
<meta charset="utf-8">
<title>OLED %(count)d frames at %(interval)dms</title>
<style>
  body { background:#15161a; color:#c8ccd4; font:14px ui-monospace,Menlo,monospace;
         display:flex; flex-direction:column; align-items:center; gap:14px;
         padding:32px 16px; margin:0; }
  #screen { width:%(w)dpx; height:%(h)dpx; background-color:#000;
            background-image:url(data:image/png;base64,%(png)s);
            background-size:%(w)dpx %(strip)dpx; background-repeat:no-repeat;
            image-rendering:pixelated; border:2px solid #3a3d45;
            border-radius:4px; cursor:pointer; }
  .row { display:flex; gap:16px; align-items:center; }
  b { color:#e8eaee; font-weight:600; }
</style>
<div id="screen" title="click to pause"></div>
<div class="row">
  <span>frame <b id="n">1</b>/%(count)d</span>
  <span><b id="t">0.00</b>s</span>
  <span id="state">playing</span>
</div>
<p>%(interval)dms a frame, the rate main.cpp refreshes the display at.
Click the screen to pause.</p>
<script>
var COUNT = %(count)d, INTERVAL = %(interval)d, H = %(h)d;
var el = document.getElementById("screen"), n = document.getElementById("n"),
    t = document.getElementById("t"), state = document.getElementById("state");
var i = 0, timer = null;
function show() {
  el.style.backgroundPosition = "0 " + (-i * H) + "px";
  n.textContent = i + 1;
  t.textContent = (i * INTERVAL / 1000).toFixed(2);
  i = (i + 1) %% COUNT;
}
function play() { timer = setInterval(show, INTERVAL); state.textContent = "playing"; }
el.onclick = function () {
  if (timer) { clearInterval(timer); timer = null; state.textContent = "paused"; }
  else play();
};
show();
play();
</script>
"""


def write_html(path, frames, scale, interval):
    """A self-contained player: one strip of every frame, stepped by CSS."""
    strip = []
    for frame in frames:
        for row in frame:
            strip.append([255 if v else 0 for v in row])

    png = base64.b64encode(png_bytes(strip, WIDTH, HEIGHT * len(frames)))

    with open(path, "w") as f:
        f.write(HTML % {
            "count": len(frames),
            "interval": interval,
            "w": WIDTH * scale,
            "h": HEIGHT * scale,
            "strip": HEIGHT * scale * len(frames),
            "png": png.decode("ascii"),
        })
    print(f"wrote {path} ({len(frames)} frames at {interval}ms, "
          f"{len(png) // 1024}kb of image)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="raw 1024 byte frame buffer dumps")
    ap.add_argument("-o", "--out", default="oled.png")
    ap.add_argument("-s", "--scale", type=int, default=3)
    ap.add_argument("--gap", type=int, default=6, help="pixels between frames")
    ap.add_argument("--html", metavar="PATH",
                    help="play the frames instead of stacking them")
    ap.add_argument("--interval", type=int, default=50,
                    help="ms a frame, matching OLED_INTERVAL_MS in main.cpp")
    args = ap.parse_args()

    frames = []
    for path in args.files:
        with open(path, "rb") as f:
            buf = f.read()
        if len(buf) != 1024:
            sys.exit(f"{path}: expected 1024 bytes, got {len(buf)}")
        frames.append(unpack(buf))

    if args.html:
        write_html(args.html, frames, args.scale, args.interval)
        return

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
