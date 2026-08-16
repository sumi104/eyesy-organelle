#!/usr/bin/env python3
"""Checks shift plus the volume knob, and the amp setting it comes out as.

The passthrough itself is a switch inside the codec, so there is nothing here
to test about the audio. What can go wrong is the control: a level that jumps
the moment shift is pressed, a knob that writes the amp sixty times a second
without having moved, or a mute that is not really a mute.

    python3 tests/test_audio_thru.py
"""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.chdir(os.path.dirname(HERE))

os.environ["EYESY_PLATFORM"] = "organelle_s"


def _install_stubs():
    liblo = types.ModuleType("liblo")
    liblo.Address = lambda *a, **k: object()
    liblo.Server = lambda *a, **k: object()
    liblo.AddressError = type("AddressError", (Exception,), {})
    liblo.ServerError = type("ServerError", (Exception,), {})
    liblo.send = lambda *a, **k: None
    sys.modules["liblo"] = liblo

    pygame = types.ModuleType("pygame")
    pygame.Surface = lambda *a, **k: object()

    class _Font:
        def __init__(self, *a, **k):
            pass

    pygame.font = types.SimpleNamespace(Font=_Font)
    pygame.image = types.SimpleNamespace(save=lambda *a, **k: None,
                                         load=lambda *a, **k: None,
                                         tobytes=lambda *a, **k: b"",
                                         frombytes=lambda *a, **k: None)
    pygame.transform = types.SimpleNamespace(scale=lambda *a, **k: None,
                                             smoothscale=lambda *a, **k: None)
    pygame.draw = types.SimpleNamespace()
    sys.modules["pygame"] = pygame


_install_stubs()

import audio_thru                       # noqa: E402
import eyesy as eyesy_module            # noqa: E402
import oled                             # noqa: E402


class RawValueTest(unittest.TestCase):
    """What a knob position asks the output amp for."""

    def test_zero_is_the_codecs_own_mute(self):
        # not 61 with a mute somewhere else, the bottom of the knob has to be
        # the value the amp treats as silence
        self.assertEqual(audio_thru.raw_value(0.0), 0)

    def test_full_is_the_top_of_the_amp(self):
        self.assertEqual(audio_thru.raw_value(1.0), audio_thru.VOL_MAX)

    def test_anything_above_zero_clears_the_mute(self):
        # the codec mutes below 48, so the first audible step has to be above
        # it rather than at the bottom of a linear map over the whole range
        self.assertGreaterEqual(audio_thru.raw_value(0.01), 48)

    def test_it_rises_with_the_knob(self):
        values = [audio_thru.raw_value(i / 10.0) for i in range(1, 11)]
        self.assertEqual(values, sorted(values))
        self.assertEqual(len(set(values)), len(values))

    def test_out_of_range_is_clamped_rather_than_trusted(self):
        self.assertEqual(audio_thru.raw_value(-1.0), 0)
        self.assertEqual(audio_thru.raw_value(9.0), audio_thru.VOL_MAX)

    def test_the_span_is_the_useful_part_of_the_amp(self):
        # 0dB sits at 121 and the steps are a dB, so this is -60dB to +6dB
        self.assertEqual(audio_thru.VOL_MIN, 61)
        self.assertEqual(audio_thru.VOL_MAX, 127)


class ThruKnobTest(unittest.TestCase):

    def setUp(self):
        oled.enabled = False
        self.e = eyesy_module.Eyesy()
        self.e.config = dict(self.e.DEFAULT_CONFIG)

        self.written = []
        audio_thru.enabled = True
        audio_thru.set_volume = lambda v: self.written.append(v)

        self.notified = []
        oled.notify_value = lambda h, v: self.notified.append((h, v))

        # there is no /sdcard here, and the tests that care about saving put
        # their own counter in its place
        self.e.save_config_file = lambda: None

    def tearDown(self):
        # these are module level, so put them back for whoever runs next
        import importlib
        importlib.reload(audio_thru)
        importlib.reload(oled)

    def shift(self, down):
        self.e.dispatch_key_event(2, 100 if down else 0)

    def turn(self, value):
        self.e.knob_hardware[4] = value
        self.e.check_thru_knob()

    # --- the setting ------------------------------------------------------

    def test_it_starts_silent_so_an_update_does_not_make_noise(self):
        self.assertEqual(self.e.DEFAULT_CONFIG["audio_thru_volume"], 0.0)

    def test_a_junk_value_in_the_config_falls_back(self):
        self.e.config["audio_thru_volume"] = 4.0
        self.e.validate_config()
        self.assertEqual(self.e.config["audio_thru_volume"], 0.0)

    # --- the knob ---------------------------------------------------------

    def test_nothing_happens_without_shift(self):
        self.turn(0.9)
        self.assertEqual(self.e.config["audio_thru_volume"], 0.0)
        self.assertEqual(self.written, [])

    def test_pressing_shift_does_not_jump_the_level_to_the_knob(self):
        # the knob is parked at the top because it was setting a mode
        # parameter. taking the level from it straight away is a shout.
        self.e.knob_hardware[4] = 1.0
        self.shift(True)
        self.turn(1.0)
        self.assertEqual(self.e.config["audio_thru_volume"], 0.0)
        self.assertEqual(self.written, [])

    def test_a_nudge_is_not_enough_to_unlock_it(self):
        self.e.knob_hardware[4] = 0.5
        self.shift(True)
        self.turn(0.53)
        self.assertEqual(self.written, [])

    def test_moving_it_takes_hold(self):
        self.e.knob_hardware[4] = 0.5
        self.shift(True)
        self.turn(0.8)
        self.assertAlmostEqual(self.e.config["audio_thru_volume"], 0.8)
        self.assertEqual(self.written, [0.8])

    def test_once_unlocked_small_moves_count_too(self):
        self.e.knob_hardware[4] = 0.5
        self.shift(True)
        self.turn(0.8)
        self.turn(0.81)
        self.assertEqual(self.written, [0.8, 0.81])

    def test_a_still_knob_is_not_written_every_frame(self):
        self.e.knob_hardware[4] = 0.5
        self.shift(True)
        self.turn(0.8)
        for _ in range(60):
            self.e.check_thru_knob()
        self.assertEqual(self.written, [0.8])
        self.assertEqual(len(self.notified), 1)

    def test_it_can_be_taken_all_the_way_down_to_silence(self):
        self.e.knob_hardware[4] = 0.5
        self.shift(True)
        self.turn(0.0)
        self.assertEqual(self.e.config["audio_thru_volume"], 0.0)
        self.assertEqual(audio_thru.raw_value(self.written[-1]), 0)

    def test_releasing_shift_relocks_it(self):
        self.e.knob_hardware[4] = 0.5
        self.shift(True)
        self.turn(0.8)
        self.shift(False)
        self.shift(True)
        self.turn(0.2)
        # 0.2 is far enough from 0.8 to unlock again, but only after the move
        self.assertEqual(self.written, [0.8, 0.2])

    def test_the_lock_is_measured_from_where_shift_was_pressed(self):
        self.e.knob_hardware[4] = 0.5
        self.shift(True)
        self.turn(0.8)
        self.shift(False)
        # shift again with the knob left at 0.8, it must not fire on its own
        self.shift(True)
        self.turn(0.8)
        self.assertEqual(self.written, [0.8])

    def test_returning_to_the_last_level_still_shows_its_bar(self):
        self.e.knob_hardware[4] = 0.5
        self.shift(True)
        self.turn(0.8)
        self.shift(False)
        # the knob went off doing mode work and came back to the same place.
        # the level is already right, but the bar has to be drawn or the knob
        # looks dead for the rest of that press
        self.e.knob_hardware[4] = 0.3
        self.shift(True)
        self.turn(0.8)
        self.assertEqual(self.written, [0.8, 0.8])
        self.assertEqual(len(self.notified), 2)

    # --- what shows on the oled -------------------------------------------

    def test_turning_it_shows_a_bar_like_the_modulation_controls(self):
        self.e.knob_hardware[4] = 0.5
        self.shift(True)
        self.turn(0.75)
        self.assertEqual(self.notified, [("Audio Thru", 0.75)])

    # --- saving -----------------------------------------------------------

    def test_the_level_is_saved_when_shift_comes_up(self):
        saves = []
        self.e.save_config_file = lambda: saves.append(True)
        self.e.knob_hardware[4] = 0.5
        self.shift(True)
        self.turn(0.8)
        self.shift(False)
        self.assertEqual(len(saves), 1)

    def test_shift_used_for_something_else_does_not_write_the_config(self):
        saves = []
        self.e.save_config_file = lambda: saves.append(True)
        self.shift(True)
        self.shift(False)
        self.assertEqual(saves, [])

    def test_gain_and_the_level_are_saved_independently(self):
        saves = []
        self.e.save_config_file = lambda: saves.append(True)
        self.e.knob_hardware[0] = 0.5
        self.e.knob_hardware[4] = 0.5
        self.shift(True)
        self.e.knob_hardware[0] = 0.9
        self.e.check_gain_knob()
        self.shift(False)
        # the gain moved and the level did not, so one save, not two
        self.assertEqual(len(saves), 1)
        self.assertEqual(self.e.config["audio_thru_volume"], 0.0)


class OffTheOrganelleTest(unittest.TestCase):
    """EYESY hardware has no bypass to open."""

    def test_init_does_nothing_without_the_platform_set(self):
        import importlib
        saved = os.environ.get("EYESY_PLATFORM", "")
        os.environ["EYESY_PLATFORM"] = ""
        try:
            importlib.reload(audio_thru)
            e = eyesy_module.Eyesy()
            e.config = dict(e.DEFAULT_CONFIG)
            audio_thru.init(e)
            self.assertFalse(audio_thru.enabled)
            # and a write in that state must not reach for a mixer that was
            # never opened
            audio_thru.set_volume(0.5)
        finally:
            os.environ["EYESY_PLATFORM"] = saved
            importlib.reload(audio_thru)


if __name__ == "__main__":
    unittest.main(verbosity=2)
