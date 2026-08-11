"""Publishes frames for the live video stream.

The render loop only pays for a nearest neighbour downscale and a memcpy into
shared memory, and only on the frames it actually sends. A separate process
does the JPEG encoding and the web server serves it as motion jpeg, so a
projector on the network shows roughly what the video output shows.

Off unless stream_enabled is set in the config.
"""

import ctypes
import os
import signal
import subprocess
import sys
import time

import pygame

import framebus

# Widths offered in the menu, the height follows the output aspect ratio.
# A width that divides the video output exactly costs the least quality:
# against the default 1280x720 that is 640 or 320.
WIDTHS = [320, 480, 640, 960]

enabled = False

_bus = None
_encoder = None
_size = (0, 0)
_scaled = None
_interval = 0.0
_next_frame = 0.0
_smooth = False

# pygame renamed this in 2.1.3, the device may be running either
_tobytes = getattr(pygame.image, "tobytes", None) or pygame.image.tostring


def _die_with_parent():
    """So a hand started engine does not leave an encoder behind."""
    try:
        PR_SET_PDEATHSIG = 1
        ctypes.CDLL("libc.so.6").prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
    except Exception:
        pass


def init(eyesy):
    """Called once the display is up. Safe to call when streaming is off."""
    global enabled, _bus, _encoder, _size, _scaled
    global _interval, _next_frame, _smooth

    enabled = bool(eyesy.config.get("stream_enabled", False))
    if not enabled:
        return

    # keeps the aspect ratio of the video output, jpeg likes even dimensions
    width, height = frame_size(eyesy)
    _size = (width, height)
    _scaled = pygame.Surface(_size)

    # Gate on elapsed time rather than counting frames. Skipping every nth of
    # 30 can only ever produce 30, 15, 10, 7.5 and so on, so asking for 12 or
    # 20 used to land on 15 either way.
    fps = max(1, min(30, int(eyesy.config.get("stream_fps", 15))))
    _interval = 1.0 / fps
    _next_frame = 0.0

    # Smooth scaling looks better going down to a size that is not an exact
    # divisor of the output, but it is much slower and it runs in the render
    # loop. Watch the frame rate on the OLED status page after turning it on.
    _smooth = bool(eyesy.config.get("stream_smooth", False))

    try:
        _bus = framebus.FrameBus(framebus.RAW_PATH, width * height * 3,
                                 create=True)
    except OSError as e:
        print(f"could not open the frame bus, streaming off: {e}")
        enabled = False
        return

    here = os.path.dirname(os.path.abspath(__file__))
    try:
        _encoder = subprocess.Popen(
            [sys.executable, os.path.join(here, "stream_encoder.py"),
             "--width", str(width), "--height", str(height),
             "--fps", str(fps)],
            cwd=here, preexec_fn=_die_with_parent)
    except Exception as e:
        print(f"could not start the stream encoder: {e}")
        enabled = False
        return

    print(f"live stream on: {width}x{height} at about {30 / _skip:.0f}fps")


def apply(eyesy):
    """Pick up a settings change without restarting the video engine."""
    close()
    init(eyesy)


def toggle(eyesy):
    """Start or stop the stream, from the OLED live page or the menu."""
    eyesy.config["stream_enabled"] = not eyesy.config.get("stream_enabled", False)
    eyesy.save_config_file()
    apply(eyesy)
    return eyesy.config["stream_enabled"]


def frame_size(eyesy):
    """What the encoder is or would be sending, as (width, height)."""
    width = eyesy.config.get("stream_width", 480)
    if width not in WIDTHS:
        width = 480
    height = int(width * eyesy.yres / eyesy.xres) & ~1
    return width, height


def describe(eyesy):
    """Short line for the OLED, like '640x360 20fps'."""
    width, height = frame_size(eyesy)
    return f"{width}x{height} {eyesy.config.get('stream_fps', 15)}fps"


def publish(surface):
    """Called every frame from the main loop."""
    global _next_frame

    if not enabled or _bus is None:
        return

    now = time.monotonic()
    if now < _next_frame:
        return
    # anchor to now rather than to the deadline, so a slow frame does not
    # leave a backlog to catch up on
    _next_frame = now + _interval

    try:
        if _smooth:
            pygame.transform.smoothscale(surface, _size, _scaled)
        else:
            pygame.transform.scale(surface, _size, _scaled)
        _bus.publish(_tobytes(_scaled, "RGB"), _size[0], _size[1])
    except Exception as e:
        print(f"stream publish failed: {e}")


def close():
    global _encoder, _bus, enabled

    enabled = False

    if _encoder is not None:
        print("stopping stream encoder")
        _encoder.terminate()
        try:
            # short, this can run from the render loop when toggling live
            _encoder.wait(timeout=1)
        except subprocess.TimeoutExpired:
            _encoder.kill()
        _encoder = None

    if _bus is not None:
        _bus.unlink()
        _bus = None

    # the encoder owns this one, clean it up on the way out
    try:
        os.unlink(framebus.JPEG_PATH)
    except OSError:
        pass
