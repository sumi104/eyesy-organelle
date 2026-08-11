#!/usr/bin/env python3
"""Checks the Organelle S front panel mapping without any hardware.

Run from engines/python:

    python3 tests/test_organelle_keys.py

Stubs out liblo and pygame so it works on a laptop.
"""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.chdir(os.path.dirname(HERE))

# the engine talks to the hardware process over osc, record what it would send
SENT = []


def _install_stubs():
    liblo = types.ModuleType("liblo")
    liblo.Address = lambda *a, **k: object()
    liblo.Server = lambda *a, **k: object()
    liblo.AddressError = type("AddressError", (Exception,), {})
    liblo.ServerError = type("ServerError", (Exception,), {})
    liblo.send = lambda target, addr, *args: SENT.append((addr, args))
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
    pygame.transform = types.SimpleNamespace(scale=lambda *a, **k: None)
    pygame.draw = types.SimpleNamespace()
    sys.modules["pygame"] = pygame


_install_stubs()

import eyesy as eyesy_module     # noqa: E402
import oled                      # noqa: E402
import organelle                 # noqa: E402


class OrganelleKeyTest(unittest.TestCase):

    def setUp(self):
        SENT.clear()
        oled.enabled = False     # nothing to draw on in a test
        self.e = eyesy_module.Eyesy()
        # normally filled in by load_config_file()
        self.e.config = dict(self.e.DEFAULT_CONFIG)
        self.e.config["key_modes"] = [""] * 12
        self.e.mode_names = ["Alpha", "Beta", "Gamma"]
        self.e.set_mode_by_index(0)
        self.e.scenes = []
        self.saved = []
        self.e.save_config_file = lambda: self.saved.append(dict(self.e.config))
        # the menu screens need pygame surfaces, not what we are testing here
        self.e.switch_menu_screen = lambda name: None

    def press(self, key):
        organelle.dispatch_key(self.e, key, 100)

    def release(self, key):
        organelle.dispatch_key(self.e, key, 0)

    def tap(self, key):
        self.press(key)
        self.release(key)

    # --- the ten eyesy panel buttons -----------------------------------

    def test_aux_toggles_osd(self):
        self.assertFalse(self.e.show_osd)
        self.tap(organelle.AUX)
        self.assertTrue(self.e.show_osd)
        self.tap(organelle.AUX)
        self.assertFalse(self.e.show_osd)

    def test_shift_and_aux_opens_menu(self):
        self.press(organelle.KEY_CS)
        self.tap(organelle.AUX)
        self.assertTrue(self.e.menu_mode)

    def test_c_sharp_is_shift(self):
        self.assertFalse(self.e.key2_status)
        self.press(organelle.KEY_CS)
        self.assertTrue(self.e.key2_status)
        self.release(organelle.KEY_CS)
        self.assertFalse(self.e.key2_status)

    def test_d_sharp_toggles_persist(self):
        self.assertTrue(self.e.auto_clear)
        self.tap(organelle.KEY_DS)
        self.assertFalse(self.e.auto_clear)

    def test_white_keys_step_mode_and_scene(self):
        self.tap(organelle.KEY_D)               # mode +
        self.assertEqual(self.e.mode, "Beta")
        self.tap(organelle.KEY_C)               # mode -
        self.assertEqual(self.e.mode, "Alpha")
        self.tap(organelle.KEY_C)               # wraps around
        self.assertEqual(self.e.mode, "Gamma")

    def test_a_grabs_and_b_triggers(self):
        self.tap(organelle.KEY_A)
        self.assertTrue(self.e.screengrab_flag)
        self.tap(organelle.KEY_B)
        self.assertTrue(self.e.trig)

    def test_shift_white_keys_move_palettes(self):
        self.press(organelle.KEY_CS)
        self.tap(organelle.KEY_D)               # fg palette +
        self.assertEqual(self.e.fg_palette, 1)
        self.tap(organelle.KEY_F)               # bg palette +
        self.assertEqual(self.e.bg_palette, 1)
        self.assertEqual(self.e.mode, "Alpha")  # mode untouched under shift

    def test_footswitch_doubles_the_trigger_key(self):
        self.tap(organelle.FOOTSWITCH)
        self.assertTrue(self.e.trig)

    # --- organelle only controls ---------------------------------------

    def test_f_sharp_toggles_audio_mute(self):
        self.tap(organelle.KEY_FS)
        self.assertTrue(self.e.audio_muted)
        self.tap(organelle.KEY_FS)
        self.assertFalse(self.e.audio_muted)

    def test_shift_f_sharp_freezes(self):
        self.press(organelle.KEY_CS)
        self.tap(organelle.KEY_FS)
        self.assertTrue(self.e.freeze)
        self.assertFalse(self.e.audio_muted)

    def test_g_sharp_toggles_clock_mute(self):
        self.tap(organelle.KEY_GS)
        self.assertTrue(self.e.midi_clock_muted)

    def test_shift_g_sharp_toggles_note_mute(self):
        self.press(organelle.KEY_CS)
        self.tap(organelle.KEY_GS)
        self.assertTrue(self.e.midi_notes_muted)
        self.assertFalse(self.e.midi_clock_muted)

    def test_shift_d_sharp_drives_the_knob_sequencer(self):
        self.press(organelle.KEY_CS)
        self.tap(organelle.KEY_DS)
        self.assertEqual(self.e.knob_seq_state, "enabled")
        self.assertTrue(self.e.auto_clear)   # persist not toggled under shift

    # --- upper octave mode slots ---------------------------------------

    def test_upper_octave_recalls_assigned_mode(self):
        self.e.key_modes[2] = "Gamma"
        self.tap(organelle.UPPER_OCTAVE_FIRST + 2)
        self.assertEqual(self.e.mode, "Gamma")

    def test_upper_octave_ignores_empty_slot(self):
        self.tap(organelle.UPPER_OCTAVE_FIRST + 5)
        self.assertEqual(self.e.mode, "Alpha")

    def test_shift_upper_octave_assigns_current_mode(self):
        self.e.set_mode_by_name("Beta")
        self.press(organelle.KEY_CS)
        self.tap(organelle.UPPER_OCTAVE_FIRST + 4)
        self.assertEqual(self.e.key_modes[4], "Beta")
        self.assertEqual(self.e.config["key_modes"][4], "Beta")
        self.assertEqual(len(self.saved), 1, "assignment should be persisted")

    def test_missing_mode_in_a_slot_does_not_crash(self):
        self.e.key_modes[0] = "DeletedMode"
        self.tap(organelle.UPPER_OCTAVE_FIRST)
        self.assertEqual(self.e.mode, "Alpha")

    def test_all_twelve_slots_are_reachable(self):
        seen = {organelle.slot_for_key(k)
                for k in range(organelle.UPPER_OCTAVE_FIRST,
                               organelle.UPPER_OCTAVE_FIRST + 12)}
        self.assertEqual(seen, set(range(12)))
        self.assertIsNone(organelle.slot_for_key(organelle.KEY_B))
        self.assertIsNone(organelle.slot_for_key(25))

    # --- the map itself -------------------------------------------------

    def test_every_eyesy_button_has_exactly_one_key(self):
        buttons = sorted(organelle.EYESY_BUTTON.values())
        # 10 is on both B and the foot switch, everything else is unique
        self.assertEqual(buttons, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10])

    def test_black_keys_are_not_wired_to_panel_buttons(self):
        for key in (organelle.KEY_FS, organelle.KEY_GS, organelle.KEY_AS):
            self.assertNotIn(key, organelle.EYESY_BUTTON)


if __name__ == "__main__":
    unittest.main(verbosity=2)
