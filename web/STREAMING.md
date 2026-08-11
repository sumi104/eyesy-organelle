# Live video streaming

Sends what the modes draw to a browser on the same network, so a laptop wired
to a projector can show the EYESY output without an HDMI run across the room.

    http://<eyesy-ip>/live

## How it fits together

    video engine  ──raw RGB──▶  /dev/shm/eyesy_frame_raw
      (main.py, 30fps)              │
                                    ▼
                            stream_encoder.py  ──JPEG──▶  /dev/shm/eyesy_frame_jpeg
                            (its own process)                  │
                                                               ▼
                                                    web/app.py  /stream.mjpg
                                                    (multipart/x-mixed-replace)

The render loop only pays for a nearest neighbour downscale and a memcpy, and
only on the frames it actually sends. JPEG encoding happens in a separate
process so it lands on another core instead of in the 30fps loop. The two
buffers are plain mmapped files in `/dev/shm` with two slots and an active
index, so a reader always has a stable frame to copy — see `framebus.py`.

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

**Smoothing** averages pixels instead of dropping them, which helps at the
sizes that do not divide evenly. It runs in the render loop though, so watch
the frame rate on the OLED status page after switching it on — if it falls
below 30 the visuals themselves are being slowed to feed the stream, and a
dividing width with smoothing off is the better trade.

**Frame rate** is free on the encoder side up to whatever it can keep up with;
what it costs is one downscale and one memcpy per published frame in the
render loop. 15 is comfortable, 30 is worth trying at 320 or 640.

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

    # the encoder should be up
    pgrep -af stream_encoder.py

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
