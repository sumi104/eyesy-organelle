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
"stream_width": 480,
"stream_fps": 12
```

Height follows the aspect ratio of the video output. Widths are 320, 480 or
640; rates are 6, 12 or 20 fps.

## What to expect

Motion JPEG on a CM3 is bound by the encoder, not the network. 480x270 at
12fps costs roughly one tenth of a core to publish and about 1-3 Mbit/s on the
wire, with well under a second of latency over decent wifi. 640 wide at 20fps
is about as far as it goes before frames start being dropped.

Motion JPEG was chosen because it needs nothing installed on the viewing
machine and no plugin, just an `<img>` tag. If the picture quality is not
enough, the next step up is H.264 through the Pi's hardware encoder
(`v4l2h264enc`) served as HLS or WebRTC — much better quality per bit, at the
cost of a GStreamer pipeline and more latency.

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
