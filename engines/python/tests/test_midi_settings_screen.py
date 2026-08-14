#!/usr/bin/env python3
"""Checks the Audio MIDI settings screen writes values back in one piece.

    python3 tests/test_midi_settings_screen.py
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

os.environ["EYESY_PLATFORM"] = "organelle_s"   # so the organelle rows appear

import eyesy as eyesy_module           # noqa: E402
import screen_midi_settings as sms     # noqa: E402


class MidiSettingsScreenTest(unittest.TestCase):

    def setUp(self):
        self.e = eyesy_module.Eyesy()
        self.e.config = dict(self.e.DEFAULT_CONFIG)
        self.e.switch_menu_screen = lambda name: None
        self.e.save_config_file = lambda: None
        self.screen = sms.ScreenMIDISettings(self.e)

    def item(self, name):
        i = self.screen.get_item_index(name)
        self.assertGreaterEqual(i, 0, f"no row for {name}")
        return self.screen.menu.items[i]

    def test_the_sync_setting_is_on_the_screen(self):
        item = self.item("knob_mod_sync")
        self.assertTrue(item.adjustable)
        self.assertEqual((item.min_value, item.max_value), (0, 1))

    def test_it_says_which_way_round_it_is(self):
        item = self.item("knob_mod_sync")
        item.value = 1
        self.screen.text_for_menu_item(item)
        self.assertIn("Synced", item.text)
        item.value = 0
        self.screen.text_for_menu_item(item)
        self.assertIn("Free", item.text)

    def test_booleans_come_back_as_booleans(self):
        # the menu holds every value as an int, and a setting validated with
        # isinstance(x, bool) would be thrown away for arriving as 0 or 1
        self.screen.before()
        for name in ("knob_mod_sync", "notes_change_mode"):
            self.item(name).value = 1
        self.screen.save_config()

        for name in ("knob_mod_sync", "notes_change_mode"):
            self.assertIsInstance(self.e.config[name], bool, name)

        # and now survive the check that runs at startup
        wanted = dict(self.e.config)
        self.e.validate_config()
        for name in ("knob_mod_sync", "notes_change_mode"):
            self.assertEqual(self.e.config[name], wanted[name],
                             f"{name} did not survive validation")

    def test_turning_it_off_survives_too(self):
        self.e.config["knob_mod_sync"] = True
        self.screen.before()
        self.item("knob_mod_sync").value = 0
        self.screen.save_config()
        self.e.validate_config()
        self.assertIs(self.e.config["knob_mod_sync"], False)

    def test_the_numbers_are_still_numbers(self):
        self.screen.before()
        self.item("midi_channel").value = 7
        self.item("knob1_cc").value = 42
        self.screen.save_config()
        self.assertEqual(self.e.config["midi_channel"], 7)
        self.assertEqual(self.e.config["knob1_cc"], 42)
        self.assertNotIsInstance(self.e.config["midi_channel"], bool)


if __name__ == "__main__":
    unittest.main(verbosity=2)
