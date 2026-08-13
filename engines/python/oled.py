"""Feeds the Organelle S OLED.

The hardware process owns the frame buffer and the page state, this module just
pushes it the numbers and strings it needs over OSC. Everything is a no-op on
EYESY hardware, which has no OLED.

The field order of send_state() has to match oledState() in
platforms/organelle_s/hw_controls/main.cpp.
"""

import os
import subprocess
import threading
import time

import helpers
import osc
import streamer

# bits of the flags field, kept in sync with OledPages.h
FLAG_TRIG       = 1 << 0
FLAG_PERSIST    = 1 << 1
FLAG_AUDIO_MUTE = 1 << 2
FLAG_CLOCK_MUTE = 1 << 3
FLAG_FREEZE     = 1 << 4
FLAG_SHIFT      = 1 << 5
FLAG_MENU       = 1 << 6
FLAG_OSD        = 1 << 7
FLAG_USB        = 1 << 8
FLAG_WIFI       = 1 << 9
FLAG_MIDI_ACT   = 1 << 10
FLAG_SEQ_PLAY   = 1 << 11
FLAG_SEQ_REC    = 1 << 12
FLAG_NOTE_MUTE  = 1 << 13
FLAG_STREAM     = 1 << 14

# bits 15 to 19, one per knob, set while its random modulation is running
FLAG_KNOB_MOD = 1 << 15

# how often the packed state message goes out, the display refreshes at 20hz
STATE_INTERVAL = 0.05

# how often the slow network lookups run
NET_INTERVAL = 5.0

enabled = False

_last_state = 0.0
_texts = {}
_trig_seen = False

# filled in by the network thread
_net = {"ssid": "off", "ip": "-", "level": 0}


def init(eyesy):
    """Called once at startup, after osc.init()."""
    global enabled
    enabled = os.environ.get("EYESY_PLATFORM", "") == "organelle_s"
    if not enabled:
        return

    send_text("ver", eyesy.VERSION)
    send_text("res", f"{eyesy.xres}x{eyesy.yres}")
    send_text("trig", eyesy.TRIGGER_SOURCES[eyesy.config["trigger_source"]])
    send_stream_info(eyesy)
    for slot, name in enumerate(eyesy.key_modes):
        send_keymap(slot, name)

    threading.Thread(target=_net_loop, daemon=True).start()


def send_stream_info(eyesy):
    """Watch address and frame size for the live page."""
    if not enabled:
        return
    send_text("sinfo", streamer.describe(eyesy))
    ip = _net["ip"]
    send_text("url", f"{ip}/live" if ip and ip != "-" else "no network")


def notify(heading, detail=""):
    """Transient full screen message, about a second.

    The heading is drawn in the big font, so it has to stay short. Anything
    that can be long, a mode name for instance, belongs in the detail line.
    """
    if not enabled:
        return
    osc.send("/oled/notify", str(heading)[:12], str(detail)[:21])


def send_text(key, value):
    """Only goes out when the value actually changed."""
    if not enabled:
        return
    value = str(value)
    if _texts.get(key) == value:
        return
    _texts[key] = value
    osc.send("/oled/text", key, value)


def send_keymap(slot, name):
    if not enabled:
        return
    osc.send("/oled/keymap", int(slot), str(name) if name else "")


def set_page(page):
    if not enabled:
        return
    osc.send("/oled/page", int(page))


def trigger():
    """Latch a trigger so a blip is not lost between refreshes."""
    global _trig_seen
    _trig_seen = True


def update(eyesy):
    """Called every frame from the main loop."""
    global _last_state, _trig_seen

    if not enabled:
        return

    if eyesy.trig:
        _trig_seen = True

    now = time.time()
    if (now - _last_state) < STATE_INTERVAL:
        return
    _last_state = now

    # strings, these are filtered so only changes go out
    send_text("mode", eyesy.mode)
    if eyesy.scene_index >= 0 and eyesy.scene_index < len(eyesy.scenes):
        send_text("scene", eyesy.scenes[eyesy.scene_index]["name"])
    else:
        send_text("scene", "none")
    send_text("ssid", _net["ssid"])
    send_text("ip", _net["ip"])
    send_text("midi", eyesy.usb_midi_name if eyesy.usb_midi_name else "none")
    send_text("trig", eyesy.TRIGGER_SOURCES[eyesy.config["trigger_source"]])
    send_text("res", f"{eyesy.xres}x{eyesy.yres}")
    send_stream_info(eyesy)

    flags = 0
    if _trig_seen:                flags |= FLAG_TRIG
    if not eyesy.auto_clear:      flags |= FLAG_PERSIST
    if eyesy.audio_muted:         flags |= FLAG_AUDIO_MUTE
    if eyesy.midi_clock_muted:    flags |= FLAG_CLOCK_MUTE
    if eyesy.midi_notes_muted:    flags |= FLAG_NOTE_MUTE
    if eyesy.freeze:              flags |= FLAG_FREEZE
    if eyesy.key2_status:         flags |= FLAG_SHIFT
    if eyesy.menu_mode:           flags |= FLAG_MENU
    if eyesy.show_osd:            flags |= FLAG_OSD
    if eyesy.running_from_usb:    flags |= FLAG_USB
    if _net["level"] > 0:         flags |= FLAG_WIFI
    if any(eyesy.midi_notes):     flags |= FLAG_MIDI_ACT
    if eyesy.knob_seq_state == "playing":   flags |= FLAG_SEQ_PLAY
    if eyesy.knob_seq_state == "recording": flags |= FLAG_SEQ_REC
    if eyesy.config.get("stream_enabled"):  flags |= FLAG_STREAM
    for i, on in enumerate(eyesy.knob_mod):
        if on: flags |= FLAG_KNOB_MOD << i
    _trig_seen = False

    osc.send(
        "/oled/state",
        _knob(eyesy.knob1), _knob(eyesy.knob2), _knob(eyesy.knob3),
        _knob(eyesy.knob4), _knob(eyesy.knob5),
        _vu(eyesy.audio_peak), _vu(eyesy.audio_peak_r),
        int(eyesy.config["audio_gain"] * 100),
        flags,
        eyesy.mode_index, len(eyesy.mode_names),
        eyesy.scene_index, len(eyesy.scenes),
        int(eyesy.fps),
        _net["level"],
        eyesy.config["midi_channel"],
        eyesy.config["knob1_cc"], eyesy.config["knob2_cc"],
        eyesy.config["knob3_cc"], eyesy.config["knob4_cc"],
        eyesy.config["knob5_cc"],
    )


def _knob(v):
    return max(0, min(1023, int(v * 1023)))


def _vu(peak):
    # the video OSD treats 30720 as full scale
    return max(0, min(100, int((peak / 30720.0) * 100)))


def _net_loop():
    """Network lookups are slow, so they live off the render thread."""
    while True:
        try:
            _net["level"] = _wifi_level()
            _net["ssid"] = _wifi_ssid() if _net["level"] > 0 else "off"
            _net["ip"] = _ip_address()
        except Exception as e:
            print(f"oled network poll failed: {e}")
        time.sleep(NET_INTERVAL)


def _wifi_level():
    """0 to 4, read straight out of /proc so it costs nothing."""
    try:
        with open("/proc/net/wireless") as f:
            lines = f.readlines()[2:]
    except OSError:
        return 0

    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            # link quality is reported out of 70
            quality = float(parts[2].rstrip("."))
        except ValueError:
            continue
        if quality <= 0:
            return 0
        return max(1, min(4, int((quality / 70.0) * 4) + 1))
    return 0


def _wifi_ssid():
    try:
        out = subprocess.run(["iwgetid", "-r"], capture_output=True,
                             text=True, timeout=3)
        name = out.stdout.strip()
        return name if name else "off"
    except Exception:
        return "off"


def _ip_address():
    return helpers.get_ip("-")
