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

    def test_footswitch_saves_a_scene(self):
        saved = []
        self.e.save_scene = lambda: saved.append(1)
        self.tap(organelle.FOOTSWITCH)
        self.assertEqual(len(saved), 1)
        self.assertFalse(self.e.trig, "the pedal no longer triggers")

    def test_holding_the_footswitch_cannot_delete_a_scene(self):
        # the save key deletes the current scene when held for a second, which
        # is what a foot resting on a pedal looks like
        deleted = []
        self.e.save_scene = lambda: None
        self.e.delete_current_scene = lambda: deleted.append(1)
        self.press(organelle.FOOTSWITCH)
        self.assertFalse(self.e.save_key_status,
                         "the pedal must not arm the delete timer")
        self.e.save_key_time = 0          # as if held far longer than a second
        self.e.update_scene_save_key()
        self.release(organelle.FOOTSWITCH)
        self.assertEqual(deleted, [])

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

    # --- upper octave white keys, mode slots ---------------------------

    def upper(self, name):
        """Raw key index of an upper octave key by name."""
        chromatic = ["C", "C#", "D", "D#", "E", "F",
                     "F#", "G", "G#", "A", "A#", "B"]
        return organelle.UPPER_OCTAVE_FIRST + chromatic.index(name)

    def test_upper_octave_recalls_assigned_mode(self):
        self.e.key_modes[2] = "Gamma"          # E
        self.tap(self.upper("E"))
        self.assertEqual(self.e.mode, "Gamma")

    def test_upper_octave_ignores_empty_slot(self):
        self.tap(self.upper("A"))
        self.assertEqual(self.e.mode, "Alpha")

    def test_shift_upper_octave_assigns_current_mode(self):
        self.e.set_mode_by_name("Beta")
        self.press(organelle.KEY_CS)
        self.tap(self.upper("G"))              # slot 4
        self.assertEqual(self.e.key_modes[4], "Beta")
        self.assertEqual(self.e.config["key_modes"][4], "Beta")
        self.assertEqual(len(self.saved), 1, "assignment should be persisted")

    def test_missing_mode_in_a_slot_does_not_crash(self):
        self.e.key_modes[0] = "DeletedMode"
        self.tap(self.upper("C"))
        self.assertEqual(self.e.mode, "Alpha")

    def test_white_keys_own_the_mode_slots_and_blacks_do_not(self):
        whites = ["C", "D", "E", "F", "G", "A", "B"]
        seen = {organelle.slot_for_key(self.upper(n)) for n in whites}
        self.assertEqual(seen, set(range(7)))
        for n in ["C#", "D#", "F#", "G#", "A#"]:
            self.assertIsNone(organelle.slot_for_key(self.upper(n)))
        self.assertIsNone(organelle.slot_for_key(organelle.KEY_B))
        self.assertIsNone(organelle.slot_for_key(25))

    # --- upper octave black keys, knob modulation ----------------------

    def test_black_keys_toggle_the_knob_above_them(self):
        for i, name in enumerate(["C#", "D#", "F#", "G#", "A#"]):
            self.assertEqual(organelle.knob_for_key(self.upper(name)), i)

    def test_modulation_toggles_on_and_off(self):
        self.assertFalse(any(self.e.knob_mod))
        self.tap(self.upper("F#"))             # knob 3
        self.assertEqual(self.e.knob_mod, [False, False, True, False, False])
        self.tap(self.upper("F#"))
        self.assertFalse(any(self.e.knob_mod))

    def run_frames(self, n, triggering=False):
        """Frames of the main loop, with or without something triggering."""
        seen = set()
        for _ in range(n):
            self.e.trig = triggering
            self.e.set_knobs()
            seen.add(round(self.e.knob2, 4))
        self.e.trig = False
        return seen

    def test_modulation_moves_the_knob_the_modes_read(self):
        self.e.knob[1] = 0.5
        self.e.set_knobs()
        self.assertEqual(self.e.knob2, 0.5)

        self.tap(self.upper("D#"))             # knob 2
        moved = self.run_frames(200, triggering=True)
        self.assertGreater(len(moved), 5, "the value should be wandering")
        self.assertTrue(all(0.0 <= v <= 1.0 for v in moved))

        # and the base position is untouched, so turning it off comes home
        self.tap(self.upper("D#"))
        self.e.set_knobs()
        self.assertEqual(self.e.knob2, 0.5)

    def test_the_wobble_is_stepped_by_the_trigger(self):
        # whatever drives the visuals drives this: audio, notes, MIDI clock and
        # Link all arrive as trig, so one hook covers all of them
        self.e.knob[1] = 0.5
        self.tap(self.upper("D#"))
        self.assertGreater(len(self.run_frames(200, triggering=True)), 5)

    def test_without_a_trigger_it_settles_and_stays(self):
        # the complaint that started this: muting the audio left it running
        self.e.knob[1] = 0.5
        self.tap(self.upper("D#"))
        self.run_frames(200, triggering=True)     # get it moving

        self.run_frames(200, triggering=False)    # now nothing is triggering
        at_rest = self.run_frames(60, triggering=False)
        self.assertEqual(len(at_rest), 1,
                         f"should have come to rest, saw {sorted(at_rest)}")

    def test_muting_the_audio_stops_it(self):
        # main.py skips the block that sets trig from audio while muted, so
        # from here that simply looks like no triggers arriving
        self.e.knob[1] = 0.5
        self.tap(self.upper("D#"))
        self.run_frames(100, triggering=True)
        self.e.audio_muted = True
        self.run_frames(200, triggering=False)
        self.assertEqual(len(self.run_frames(60, triggering=False)), 1)

    def test_free_running_is_still_available_in_the_config(self):
        self.e.config["knob_mod_sync"] = False
        self.e.knob[1] = 0.5
        self.tap(self.upper("D#"))
        self.assertGreater(len(self.run_frames(300, triggering=False)), 5,
                           "unsynced it keeps its own time")

    def test_modulation_stays_inside_the_range_at_the_extremes(self):
        for base in (0.0, 1.0):
            self.e.knob_mod = [False] * 5
            self.e.knob[0] = base
            self.tap(self.upper("C#"))
            for _ in range(300):
                self.e.trig = True
                self.e.set_knobs()
                self.assertGreaterEqual(self.e.knob1, 0.0)
                self.assertLessEqual(self.e.knob1, 1.0)
            self.e.trig = False
            self.tap(self.upper("C#"))

    def test_a_scene_stores_the_set_position_not_the_wobble(self):
        self.e.knob[0] = 0.5
        self.e.set_knobs()
        self.tap(self.upper("C#"))
        for _ in range(50):
            self.e.trig = True
            self.e.set_knobs()
        self.e.trig = False
        self.assertNotEqual(self.e.knob1, 0.5, "modulation should be active")
        self.assertEqual(self.e.knob_base[0], 0.5)

    def test_modulation_keeps_running_while_shift_is_held(self):
        self.e.knob[3] = 0.5
        self.e.set_knobs()
        self.tap(self.upper("G#"))             # knob 4
        self.press(organelle.KEY_CS)
        moved = set()
        for _ in range(200):
            self.e.trig = True
            self.e.set_knobs()
            moved.add(round(self.e.knob4, 4))
        self.e.trig = False
        self.assertGreater(len(moved), 5)

    # --- a modulating knob shapes the wobble ---------------------------

    def turn(self, knob, position):
        self.e.knob_hardware[knob] = position
        self.e.update_knobs_and_notes()

    def test_turning_a_modulating_knob_sets_the_rate(self):
        self.e.knob_hardware[2] = 0.2
        self.tap(self.upper("F#"))              # knob 3
        before = self.e.knob_mod_rate[2]

        self.turn(2, 0.2)                       # picks the knob up
        self.turn(2, 0.21)                      # inside the dead band
        self.assertEqual(self.e.knob_mod_rate[2], before,
                         "a nudge must not grab the value")

        self.turn(2, 0.9)
        self.assertNotEqual(self.e.knob_mod_rate[2], before)
        self.assertLessEqual(self.e.knob_mod_rate[2],
                             self.e.KNOB_MOD_RATE_MAX)
        self.assertGreaterEqual(self.e.knob_mod_rate[2],
                                self.e.KNOB_MOD_RATE_MIN)

    def test_the_rate_knob_covers_the_whole_range(self):
        self.tap(self.upper("C#"))
        self.turn(0, 0.2)
        self.turn(0, 0.0)
        self.assertAlmostEqual(self.e.knob_mod_rate[0],
                               self.e.KNOB_MOD_RATE_MIN, places=4)
        self.turn(0, 1.0)
        self.assertAlmostEqual(self.e.knob_mod_rate[0],
                               self.e.KNOB_MOD_RATE_MAX, places=4)

    def test_holding_the_black_key_turns_its_knob_into_depth(self):
        self.tap(self.upper("D#"))              # knob 2 modulating
        self.turn(1, 0.2)
        self.turn(1, 0.9)
        rate = self.e.knob_mod_rate[1]

        self.press(self.upper("D#"))            # held, not tapped
        self.turn(1, 0.9)                       # re-picked up as depth
        self.turn(1, 0.4)
        self.assertAlmostEqual(self.e.knob_mod_depth[1], 0.4)
        self.assertEqual(self.e.knob_mod_rate[1], rate,
                         "holding the key must not also move the rate")

        # releasing after using it as a modifier must not switch it off
        self.release(self.upper("D#"))
        self.assertTrue(self.e.knob_mod[1])

    def test_a_playing_knob_sequence_blocks_the_wobble(self):
        # the sequence is writing those knobs, so a wobble on top would be two
        # things driving one control
        self.e.knob_seq_state = "playing"
        self.tap(self.upper("F#"))
        self.assertFalse(self.e.knob_mod[2], "must not switch on")

        self.e.knob_seq_state = "stopped"
        self.tap(self.upper("F#"))
        self.assertTrue(self.e.knob_mod[2], "and works again once it stops")

    def test_an_already_running_wobble_can_still_be_switched_off(self):
        self.tap(self.upper("F#"))
        self.assertTrue(self.e.knob_mod[2])
        self.e.knob_seq_state = "playing"
        self.tap(self.upper("F#"))
        self.assertFalse(self.e.knob_mod[2], "turning it off stays allowed")

    def test_recording_and_armed_do_not_block_it(self):
        for state in ("recording", "enabled", "stopped"):
            self.e.knob_mod = [False] * 5
            self.e.knob_seq_state = state
            self.tap(self.upper("F#"))
            self.assertTrue(self.e.knob_mod[2], state)

    def test_a_tap_toggles_but_a_hold_and_turn_does_not(self):
        key = self.upper("F#")                  # knob 3
        self.tap(key)
        self.assertTrue(self.e.knob_mod[2])

        self.press(key)
        self.turn(2, 0.2)
        self.turn(2, 0.8)                       # used as a modifier
        self.release(key)
        self.assertTrue(self.e.knob_mod[2], "still modulating")
        self.assertAlmostEqual(self.e.knob_mod_depth[2], 0.8)

        self.tap(key)                           # a plain tap still works
        self.assertFalse(self.e.knob_mod[2])

    def test_the_toggle_happens_on_release(self):
        key = self.upper("A#")
        self.press(key)
        self.assertFalse(self.e.knob_mod[4], "nothing until the key is let go")
        self.release(key)
        self.assertTrue(self.e.knob_mod[4])

    def test_shift_is_no_longer_involved(self):
        self.tap(self.upper("C#"))              # knob 1 modulating
        self.turn(0, 0.2)
        self.turn(0, 0.9)
        rate = self.e.knob_mod_rate[0]
        depth = self.e.knob_mod_depth[0]

        self.press(organelle.KEY_CS)
        self.turn(0, 0.4)
        self.assertEqual(self.e.knob_mod_depth[0], depth,
                         "shift is the gain, not the depth")
        self.assertNotEqual(self.e.knob_mod_rate[0], rate,
                            "the knob still sets the rate under shift")

    def test_a_modulating_knob_does_not_move_its_own_value(self):
        self.e.knob_hardware[3] = 0.2
        self.e.knob[3] = 0.5
        self.e.set_knobs()
        self.tap(self.upper("G#"))              # knob 4
        self.turn(3, 0.9)
        self.assertEqual(self.e.knob_base[3], 0.5)

    def test_switching_modulation_off_leaves_the_value_alone(self):
        self.e.knob_hardware[3] = 0.2
        self.e.knob[3] = 0.5
        self.e.set_knobs()
        self.tap(self.upper("G#"))
        self.turn(3, 0.9)                       # knob is now far from 0.5
        self.tap(self.upper("G#"))              # off

        self.e.update_knobs_and_notes()
        self.e.set_knobs()
        self.assertEqual(self.e.knob4, 0.5, "the value must not snap")

        # and it comes back under control once the knob is actually moved
        self.turn(3, 0.3)
        self.e.set_knobs()
        self.assertAlmostEqual(self.e.knob4, 0.3)

    def test_shift_knob1_still_sets_the_gain_when_not_modulating(self):
        self.press(organelle.KEY_CS)
        self.e.knob_hardware[0] = 0.9
        self.e.check_gain_knob()
        self.assertAlmostEqual(self.e.config["audio_gain"], 0.9)

    def test_shift_knob1_still_sets_the_gain_while_modulating(self):
        # the depth modifier is the black key now, so shift is left alone
        self.tap(self.upper("C#"))              # knob 1 modulating
        self.press(organelle.KEY_CS)
        self.e.knob_hardware[0] = 0.9
        self.e.check_gain_knob()
        self.assertAlmostEqual(self.e.config["audio_gain"], 0.9)

    def test_each_knob_keeps_its_own_rate_and_depth(self):
        self.tap(self.upper("C#"))
        self.tap(self.upper("A#"))              # knobs 1 and 5
        self.turn(0, 0.2)
        self.turn(0, 0.9)
        self.turn(4, 0.2)
        self.turn(4, 0.1)
        self.assertNotEqual(self.e.knob_mod_rate[0], self.e.knob_mod_rate[4])
        self.assertEqual(self.e.knob_mod_rate[1], self.e.knob_mod_rate[2],
                         "untouched knobs keep the configured rate")

    # --- modulation in scenes ------------------------------------------

    def test_a_scene_carries_the_modulation_state(self):
        self.tap(self.upper("F#"))              # knob 3 on
        self.turn(2, 0.2)
        self.turn(2, 0.9)                       # its own rate
        fields = self.e._scene_fields()

        entries = fields["knob_mod"]
        self.assertEqual([e["on"] for e in entries],
                         [False, False, True, False, False])
        self.assertEqual(entries[2]["rate"], self.e.knob_mod_rate[2])
        self.assertEqual(entries[2]["depth"], self.e.knob_mod_depth[2])

    def test_recalling_puts_the_modulation_back(self):
        self.tap(self.upper("D#"))
        self.turn(1, 0.2)
        self.turn(1, 0.9)
        saved = self.e._scene_fields()["knob_mod"]

        self.tap(self.upper("D#"))              # off again
        self.assertFalse(any(self.e.knob_mod))

        self.e.apply_scene_knob_mod(saved)
        self.assertEqual(self.e.knob_mod[1], True)
        self.assertAlmostEqual(self.e.knob_mod_rate[1], saved[1]["rate"])
        self.assertAlmostEqual(self.e.knob_mod_depth[1], saved[1]["depth"])

    def test_recall_makes_the_knobs_pick_up_again(self):
        # the knobs have not moved while the scene was away, so a knob left
        # at one end must not slam the rate across on the next frame
        self.tap(self.upper("C#"))
        self.turn(0, 0.2)
        self.turn(0, 0.9)
        rate = self.e.knob_mod_rate[0]

        self.e.apply_scene_knob_mod(self.e._scene_fields()["knob_mod"])
        self.e.update_knobs_and_notes()
        self.assertEqual(self.e.knob_mod_rate[0], rate)

    def test_a_scene_from_before_this_existed_still_loads(self):
        for missing in (None, [], {}, "nope"):
            entries = self.e._validate_scene_knob_mod(missing)
            self.assertEqual(len(entries), 5)
            self.assertFalse(any(e["on"] for e in entries))
            self.assertTrue(all(e["rate"] == self.e.config["knob_mod_rate"]
                                for e in entries))

    def test_junk_in_a_scene_falls_back_rather_than_crashing(self):
        junk = [
            {"on": "yes", "rate": 99, "depth": -1},   # out of range
            {"on": True, "rate": None},               # wrong type
            {},                                       # empty
            {"on": True, "rate": True, "depth": 0.4}, # bool is not a rate
            "not a dict",
        ]
        entries = self.e._validate_scene_knob_mod(junk)
        self.assertEqual(len(entries), 5)
        self.assertFalse(entries[0]["on"], "a string is not True")
        self.assertEqual(entries[0]["rate"], self.e.config["knob_mod_rate"])
        self.assertEqual(entries[0]["depth"], self.e.config["knob_mod_depth"])
        self.assertTrue(entries[1]["on"])
        self.assertEqual(entries[3]["rate"], self.e.config["knob_mod_rate"])
        self.assertAlmostEqual(entries[3]["depth"], 0.4)
        for e in entries:
            self.assertTrue(0 < e["rate"] <= 1)
            self.assertTrue(0 <= e["depth"] <= 1)

    def test_a_scene_survives_the_trip_through_json(self):
        # save_scene json.dumps this, and a value that will not serialise
        # would only show up when saving on the instrument
        import json
        self.tap(self.upper("A#"))
        restored = json.loads(json.dumps(self.e._scene_fields()))

        for key in ("mode", "knob1", "knob2", "knob3", "knob4", "knob5",
                    "auto_clear", "bg_palette", "fg_palette", "knob_mod"):
            self.assertIn(key, restored)
        self.assertEqual(len(restored["knob_mod"]), 5)
        self.assertTrue(restored["knob_mod"][4]["on"])

        # and comes back out of validation unchanged
        entries = self.e._validate_scene_knob_mod(restored["knob_mod"])
        self.assertEqual(entries, restored["knob_mod"])

    # --- config -------------------------------------------------------

    def test_an_old_twelve_slot_config_keeps_its_white_keys(self):
        # the black keys of the upper octave became knob modulation, so a
        # config written before that has to be carried over, not truncated
        chromatic = ["cMode", "cs", "dMode", "ds", "eMode", "fMode",
                     "fs", "gMode", "gs", "aMode", "as", "bMode"]
        self.e.config["key_modes"] = list(chromatic)
        self.e._validate_config_key_modes()
        self.assertEqual(self.e.key_modes,
                         ["cMode", "dMode", "eMode", "fMode",
                          "gMode", "aMode", "bMode"])
        self.assertEqual(self.e.config["key_modes"], self.e.key_modes)

    def test_key_modes_config_is_always_seven_strings(self):
        for bad in (None, [], ["only one"], list(range(20)), "nope",
                    [""] * 7, [""] * 12):
            self.e.config["key_modes"] = bad
            self.e._validate_config_key_modes()
            self.assertEqual(len(self.e.key_modes), 7, f"from {bad!r}")
            self.assertTrue(all(isinstance(s, str) for s in self.e.key_modes))

    # --- the map itself -------------------------------------------------

    def test_every_eyesy_button_has_exactly_one_key(self):
        buttons = sorted(organelle.EYESY_BUTTON.values())
        self.assertEqual(buttons, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        self.assertNotIn(organelle.FOOTSWITCH, organelle.EYESY_BUTTON,
                         "the pedal is handled on its own, not as a button")

    def test_black_keys_are_not_wired_to_panel_buttons(self):
        for key in (organelle.KEY_FS, organelle.KEY_GS, organelle.KEY_AS):
            self.assertNotIn(key, organelle.EYESY_BUTTON)


if __name__ == "__main__":
    unittest.main(verbosity=2)
