#!/usr/bin/env python3
"""Checks what goes out over /oled/notify.

Both lines are drawn in the same small font now, so the caps here are what
keeps a long mode name from running off the right hand edge. The warning flag
is what picks the ! marker over the i, so the messages that report a refusal
have to be the ones that set it.

    python3 tests/test_notify.py
"""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.chdir(os.path.dirname(HERE))


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

import eyesy as eyesy_module        # noqa: E402
import oled                         # noqa: E402
import organelle                    # noqa: E402

# the upper octave keys these tests press
PALETTE_KEY_FG = organelle.UPPER_C
MOD_KEY_KNOB2 = next(k for k, i in organelle.KNOB_MOD_KEYS.items() if i == 1)

# what the small font fits, from the x each line starts at in renderNotify()
HEADING_MAX = 18
DETAIL_MAX = 20


class _Osc:
    def __init__(self):
        self.sent = []

    def send(self, address, *args):
        if address == "/oled/notify":
            self.sent.append(args)


class NotifyTest(unittest.TestCase):

    def setUp(self):
        self.osc = _Osc()
        oled.osc = self.osc
        oled.enabled = True
        self.addCleanup(setattr, oled, "enabled", False)

        self.e = eyesy_module.Eyesy()
        self.e.config = dict(self.e.DEFAULT_CONFIG)
        self.e.mode_names = ["Alpha", "Beta"]
        self.e.set_mode_by_index(0)
        self.e.scenes = []
        self.e.switch_menu_screen = lambda name: None
        self.e.save_config_file = lambda: None
        self.e.recall_scene = lambda i: None

    def last(self):
        self.assertTrue(self.osc.sent, "nothing was sent")
        return self.osc.sent[-1]

    def tap(self, key):
        organelle.dispatch_key(self.e, key, 100)
        organelle.dispatch_key(self.e, key, 0)

    # --- the message itself ----------------------------------------------

    def test_it_carries_a_warning_flag(self):
        oled.notify("Heading", "detail")
        self.assertEqual(self.last(), ("Heading", "detail", 0))
        oled.warn("Heading", "detail")
        self.assertEqual(self.last(), ("Heading", "detail", 1))

    def test_one_line_still_sends_an_empty_second(self):
        oled.notify("Audio Muted")
        self.assertEqual(self.last(), ("Audio Muted", "", 0))

    def test_both_lines_are_cut_to_what_fits(self):
        oled.notify("H" * 40, "D" * 40)
        heading, detail, _ = self.last()
        self.assertEqual(len(heading), HEADING_MAX)
        self.assertEqual(len(detail), DETAIL_MAX)

    def test_the_bar_fits_the_detail_line(self):
        for fraction in (0.0, 0.5, 1.0):
            oled.notify_value("Depth 1", fraction)
            _, detail, warn = self.last()
            self.assertLessEqual(len(detail), DETAIL_MAX)
            self.assertEqual(warn, 0, "adjusting a value is not a warning")

    def test_a_long_mode_name_survives_in_the_detail_line(self):
        # the reason the detail line gets the full width and no marker
        oled.notify("C# set", "Bounce Bounce Bounce")
        self.assertEqual(self.last()[1], "Bounce Bounce Bounce")

    def test_nothing_goes_out_on_eyesy_hardware(self):
        oled.enabled = False
        oled.notify("Heading", "detail")
        oled.warn("Heading", "detail")
        self.assertEqual(self.osc.sent, [])

    # --- which call sites are warnings ------------------------------------

    def test_switching_a_palette_wobble_on_does_not_warn(self):
        self.tap(PALETTE_KEY_FG)
        heading, detail, warn = self.last()
        self.assertEqual(heading, "FG Palette")
        # it says how often it will move, which is the thing you cannot see
        self.assertIn("every", detail)
        self.assertEqual(warn, 0)

    def test_switching_a_palette_wobble_off_does_not_warn(self):
        self.tap(PALETTE_KEY_FG)
        self.tap(PALETTE_KEY_FG)
        self.assertEqual(self.last(), ("FG Palette", "steady", 0))

    def test_modulation_refused_by_the_sequencer_warns(self):
        self.e.knob_seq_state = "playing"
        self.tap(MOD_KEY_KNOB2)
        heading, detail, warn = self.last()
        self.assertEqual(warn, 1, detail)
        self.assertIn("seq", detail)

    def test_modulation_going_on_does_not_warn(self):
        self.tap(MOD_KEY_KNOB2)
        self.assertEqual(self.last(), ("Knob 2", "modulating", 0))

    def test_auto_random_with_no_scenes_warns(self):
        self.tap(organelle.KEY_AS)          # modes
        self.tap(organelle.KEY_AS)          # scenes, and there are none
        self.assertEqual(self.last(), ("Auto Random", "no scenes to pick", 1))

    def test_the_mutes_report_rather_than_warn(self):
        for toggle in (self.e.toggle_audio_mute, self.e.toggle_freeze,
                       self.e.toggle_midi_clock_mute,
                       self.e.toggle_midi_notes_mute):
            toggle()
            self.assertEqual(self.last()[2], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
