# Live video streaming

Sends what the modes draw to a browser on the same network, so a laptop wired
to a projector can show the EYESY output without an HDMI run across the room.

    http://<eyesy-ip>/live

## How it fits together

    video engine  ──surface memory──▶  /dev/shm/eyesy_frame_raw
      (main.py, 30fps)                     │
                                           ▼
                            stream_encoder.py   scales, then JPEG
                            (its own process)       │
                                                    ▼
                                         /dev/shm/eyesy_frame_jpeg
                                                    │
                                                    ▼
                                         web/app.py  /stream.mjpg
                                         (multipart/x-mixed-replace)

Everything the render loop does here it does thirty times a second on top of
drawing, against a frame budget of 33ms, so it does as little as possible: one
copy of the mode surface's own memory into shared memory, no scaling and no
pixel format conversion. The encoder process rebuilds the surface on another
core from identical masks, scales it and encodes it.

That matters. Scaling in the render loop costs 15-25ms a frame at 960 wide
with smoothing, which is most of the budget and shows up as stutter on the
video output itself. If the surface cannot be passed through untouched the
engine falls back to scaling before it publishes and says so in the log.

The two buffers are plain mmapped files in `/dev/shm` with two slots and an
active index, so a reader always has a stable frame to copy — see
`framebus.py`.

The stream carries the mode surface, not the display, so the OSD and the
settings menus stay off the projector.

## Turning it on

On an Organelle S, the fastest way is the OLED: turn the encoder to the
**LIVE** page and press it. The page shows whether the stream is running, the
address to open in a browser, and the frame size and rate. Pressing again
stops it. Nothing restarts, so this is safe to do mid set. The dot next to
the page number is the display's way of saying the press does something here.

Otherwise: **Settings → Video Settings → Live Video Stream** on the video
output. Size and frame rate can be changed there and take effect immediately.

Or in `/sdcard/System/config.json`:

```json
"stream_enabled": true,
"stream_width": 640,
"stream_fps": 15,
"stream_smooth": false
```

Height follows the aspect ratio of the video output. Widths are 320, 480, 640
or 960; rates are 10, 15, 20 or 30 fps.

## Getting a better picture

**Pick a width that divides the video output.** Against the default 1280x720
output, 640 is an exact halving and 320 an exact quarter. 480 and 960 are not,
and scaling picks pixels unevenly, which is the harsh stair stepping you see
when the browser then blows the image back up to fill a projector. 640 is the
sweet spot: twice the detail of 480 and cleaner than 960.

**Smoothing** averages pixels instead of dropping them, which is what makes
960 and 480 usable. It runs in the encoder process, so it costs the video
output nothing — leave it on unless the encoder cannot keep up.

**Frame rate** costs one copy of the mode surface per published frame in the
render loop, a few milliseconds at 1280x720, so 30 is reasonable. Watch the
frame rate on the OLED status page: if it sits below 30 the visuals are being
slowed to feed the stream.

## What to expect

Motion JPEG on a CM3 is bound by the JPEG encoder, not the network. 640x360 at
15fps runs around 2-5 Mbit/s with well under a second of latency on decent
wifi. 960 wide is where the encoder starts to be the limit.

pygame gives no control over JPEG quality, so size and rate are the only dials
here. Motion JPEG was chosen because it needs nothing installed at the viewing
end, just an `<img>` tag. If this is still not enough, the next step up is
H.264 through the Pi's hardware encoder (`v4l2h264enc`) served as HLS or
WebRTC — far better quality per bit, at the cost of a GStreamer pipeline and
more latency.

## Checking it

With the engine running and streaming on:

    # the encoder should be up, and its arguments say which path is in use.
    # --src-bits present means the render loop is only copying
    pgrep -af stream_encoder.py

    # the engine says the same thing on startup
    journalctl -u eyesypy --no-pager | grep "live stream"

    # both buffers should exist
    ls -l /dev/shm/eyesy_frame_*

    # is the web server seeing frames
    curl -s localhost:8080/stream_status

    # pull a few frames
    curl -s --max-time 3 localhost:8080/stream.mjpg | wc -c

`/stream_status` returns `{"running": false}` when the engine is not
publishing, which is what the viewer page polls to show its hint.

## Notes

- `web/app.py` imports `framebus` from `engines/python`, so the two
  directories need to stay where they are relative to each other.
- Port 80 is redirected to 8080 by `eyesysetup.sh`, so the `/live` URL works
  without a port number.
- Each viewer holds one server thread for as long as the tab is open. The
  Flask server runs threaded; if `waitress-serve` is used instead, raise
  `--threads` above the default of four.
