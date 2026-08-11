"""Publishes frames for the live video stream.

Whatever the render loop does here, it does thirty times a second on top of
drawing, and the frame budget is only 33ms. So it does as close to nothing as
it can: hand the mode surface's own memory to shared memory and let the
encoder process, on another core, do the scaling and the JPEG.

Scaling in the render loop instead costs 15-25ms a frame at 960 wide with
smoothing, which is most of the budget and shows up as stutter on the video
output. That path is still here as a fallback for when the surface cannot be
passed through untouched.

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

# the surface the modes draw on, remembered so a settings change can restart
# the stream without every caller having to carry it around
_surface = None

# when true the render loop hands over untouched pixels and the encoder does
# the scaling, which is the whole point of the exercise
_passthrough = False

# pygame renamed this in 2.1.3, the device may be running either
_tobytes = getattr(pygame.image, "tobytes", None) or pygame.image.tostring


def _die_with_parent():
    """So a hand started engine does not leave an encoder behind."""
    try:
        PR_SET_PDEATHSIG = 1
        ctypes.CDLL("libc.so.6").prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
    except Exception:
        pass


def _probe_passthrough(surface):
    """Can the encoder rebuild this surface from its raw bytes?

    Returns (bitsize, masks) when it can. Rather than naming a pixel format,
    which is easy to get subtly wrong and shows up as swapped colours, the
    encoder builds a surface with identical masks and writes the bytes
    straight in. Either that works exactly or it raises.
    """
    try:
        bits = surface.get_bitsize()
        masks = surface.get_masks()
        expected = surface.get_width() * surface.get_height() * (bits // 8)

        # a non contiguous surface, one with padding at the end of each row,
        # cannot be handed over as a flat block
        view = surface.get_view('0')
        if view.length != expected:
            raise ValueError(f"surface is {view.length} bytes, expected {expected}")

        # and prove the far end can reconstruct it before relying on it
        probe = pygame.Surface((4, 4), 0, bits, masks)
        probe.get_view('0').write(b"\0" * (4 * 4 * (bits // 8)))
        return bits, masks
    except Exception as e:
        print(f"stream: cannot pass frames through untouched ({e}),"
              " falling back to scaling in the render loop")
        return None


def init(eyesy, surface=None):
    """Called once the display is up. Safe to call when streaming is off.

    surface is the one the modes draw on, used to work out whether its pixels
    can be handed to the encoder as they are. It is remembered, so restarting
    the stream later does not need it again.
    """
    global enabled, _bus, _encoder, _size, _scaled
    global _interval, _next_frame, _smooth, _passthrough, _surface

    if surface is not None:
        _surface = surface

    enabled = bool(eyesy.config.get("stream_enabled", False))
    if not enabled:
        return

    # keeps the aspect ratio of the video output, jpeg likes even dimensions
    width, height = frame_size(eyesy)
    _size = (width, height)

    # Gate on elapsed time rather than counting frames. Skipping every nth of
    # 30 can only ever produce 30, 15, 10, 7.5 and so on, so asking for 12 or
    # 20 used to land on 15 either way.
    fps = max(1, min(30, int(eyesy.config.get("stream_fps", 15))))
    _interval = 1.0 / fps
    _next_frame = 0.0

    _smooth = bool(eyesy.config.get("stream_smooth", False))

    fmt = _probe_passthrough(_surface) if _surface is not None else None
    _passthrough = fmt is not None
    _scaled = None if _passthrough else pygame.Surface(_size)

    if _passthrough:
        bits, masks = fmt
        src_w, src_h = _surface.get_size()
        capacity = src_w * src_h * (bits // 8)
    else:
        bits, masks = 0, (0, 0, 0, 0)
        src_w, src_h = width, height
        capacity = width * height * 3

    try:
        _bus = framebus.FrameBus(framebus.RAW_PATH, capacity, create=True)
    except OSError as e:
        print(f"could not open the frame bus, streaming off: {e}")
        enabled = False
        return

    here = os.path.dirname(os.path.abspath(__file__))
    args = [sys.executable, os.path.join(here, "stream_encoder.py"),
            "--width", str(width), "--height", str(height),
            "--fps", str(fps)]
    if _passthrough:
        args += ["--src-bits", str(bits),
                 "--src-masks", ",".join(str(m) for m in masks)]
        if _smooth:
            args.append("--smooth")

    try:
        _encoder = subprocess.Popen(args, cwd=here, preexec_fn=_die_with_parent)
    except Exception as e:
        print(f"could not start the stream encoder: {e}")
        enabled = False
        return

    how = "passthrough" if _passthrough else "scaled in engine"
    print(f"live stream on: {width}x{height} at {fps}fps, {how}"
          f"{', smoothed' if _smooth else ''}")


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
    width = eyesy.config.get("stream_width", 640)
    if width not in WIDTHS:
        width = 640
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
        if _passthrough:
            # one copy of the surface memory and nothing else
            _bus.publish(surface.get_view('0'), *surface.get_size())
        else:
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
