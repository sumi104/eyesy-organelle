"""Line in straight to line out, through the codec's own analogue bypass.

The WM8731 can route its line input into the output mixer inside the chip,
without the signal going anywhere near the ADC, the I2S bus or the CPU.
Switching that on is one register write, and after it the passthrough costs
nothing at all: no samples are copied, no thread runs, and the frame rate
never sees it. That is the whole reason this exists. Reading the capture
stream back out through a playback stream would have put the audio in the
same place as the drawing, where one late frame turns into a click.

Nothing else on the instrument plays back - there is no Pd here - so the
codec's output amp is free to be the level control for it. Shift and the
volume knob write it, and zero is the codec's own mute, so the feature needs
no separate on/off switch to get lost in a menu.

All of this is a no-op on EYESY hardware, which has no such bypass.
"""

import os
import subprocess

# substring of the ALSA long name, the same card sound.py captures from
CARD_MATCH = "audioinjector"

# The DAPM switch that closes the analogue path. It comes from the wm8731
# codec driver, so the name is stable in a way a numid is not.
BYPASS_CONTROL = "Output Mixer Line Bypass Switch"

# simple mixer element behind "Master Playback Volume"
VOLUME_CONTROL = "Master"

# The output amp takes 0 to 127 at a dB a step, with 0dB at 121, so the top of
# it is +6dB. The codec mutes below 48 anyway and the stretch just above that
# is inaudible, so the knob spans -60dB to +6dB and keeps a real mute of its
# own at the bottom instead of spending a third of its travel on silence.
VOL_RAW_MAX = 127
VOL_MIN = 61
VOL_MAX = 127

enabled = False

_alsa = None
_mixer = None
_last_raw = None


def init(eyesy):
    """Set the saved level, then open the analogue path.

    In that order. If anything here fails halfway the bypass stays shut, which
    is the quiet outcome - the amp comes up at +1dB from the factory and
    opening the path before the level is known would put the input through it
    at whatever that happens to be.
    """
    global enabled, _alsa, _mixer

    enabled = False
    if os.environ.get("EYESY_PLATFORM", "") != "organelle_s":
        return

    try:
        import alsaaudio
    except ImportError as e:
        print(f"audio thru off, no alsaaudio: {e}")
        return
    _alsa = alsaaudio

    card = _find_card()
    if card is None:
        print(f"audio thru off, no {CARD_MATCH} card")
        return

    try:
        _mixer = alsaaudio.Mixer(control=VOLUME_CONTROL, cardindex=card)
    except Exception as e:
        print(f"audio thru off, no {VOLUME_CONTROL} mixer: {e}")
        return

    if not _write_volume(eyesy.config["audio_thru_volume"]):
        print("audio thru off, could not set the level")
        return

    # The bypass is a DAPM control with no simple mixer element behind it, so
    # it goes through amixer rather than the handle above. It is written once
    # at startup and never again, which is what makes a subprocess fine here.
    try:
        subprocess.run(
            ["amixer", "-q", "-c", str(card), "cset",
             f"name={BYPASS_CONTROL}", "on"],
            check=True, capture_output=True)
    except Exception as e:
        print(f"audio thru off, could not open the bypass: {e}")
        return

    enabled = True
    print(f"audio thru on, card {card}, level {eyesy.config['audio_thru_volume']:.2f}")


def set_volume(fraction):
    """0 is the codec's own mute, 1 is the top of the output amp."""
    if not enabled:
        return
    _write_volume(fraction)


def raw_value(fraction):
    """The amp setting a knob position comes out as. Separated out so a test
    can check the mute and the range without an ALSA card in the room."""
    fraction = max(0.0, min(1.0, float(fraction)))
    if fraction <= 0.0:
        return 0
    return VOL_MIN + int(round(fraction * (VOL_MAX - VOL_MIN)))


def _write_volume(fraction):
    """True if the amp is now at the asked for level."""
    global _last_raw

    raw = raw_value(fraction)
    if raw == _last_raw:
        return True

    try:
        try:
            _mixer.setvolume(raw, units=_alsa.VOLUME_UNITS_RAW)
        except (AttributeError, TypeError):
            # pyalsaaudio before 0.9 has no raw units. Percent lands within a
            # step of the same place, which is under a dB.
            _mixer.setvolume(int(round(raw * 100.0 / VOL_RAW_MAX)))
    except Exception as e:
        print(f"audio thru volume write failed: {e}")
        return False

    _last_raw = raw
    return True


def _find_card():
    """ALSA index of the codec, the way sound.py looks for it."""
    try:
        for index in _alsa.card_indexes():
            if CARD_MATCH in _alsa.card_name(index)[1].lower():
                return index
    except Exception as e:
        print(f"audio thru card lookup failed: {e}")
    return None
