#!/usr/bin/env python3
"""The upper octave white keys, after Mode Keys was taken off them.

C and D wobble a palette, E steps the MIDI channel. The wobble runs on the
Auto Random Cycle clock rather than the trigger, which is the one thing about
it that is not like the knob wobble and the thing most likely to get wired up
the other way by mistake.

    python3 tests/test_palette_mod.py
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

import eyesy as eyesy_module        # noqa: E402
import oled                         # noqa: E402
import organelle                    # noqa: E402


class Base(unittest.TestCase):

    def setUp(self):
        oled.enabled = False
        self.e = eyesy_module.Eyesy()
        self.e.config = dict(self.e.DEFAULT_CONFIG)
        self.e.mode_names = ["Alpha", "Beta"]
        self.e.set_mode_by_index(0)
        self.e.scenes = []
        self.saved = []
        self.e.save_config_file = lambda: self.saved.append(dict(self.e.config))
        # enough palettes that "not the one showing" is a real choice
        self.e.palettes = [f"p{i}" for i in range(8)]

    def tap(self, k):
        organelle.dispatch_key(self.e, k, 100)
        organelle.dispatch_key(self.e, k, 0)


class PaletteModTest(Base):

    def test_it_starts_off(self):
        self.assertEqual(self.e.palette_mod, [False, False])

    def test_c_and_d_toggle_their_own_palette(self):
        self.tap(organelle.UPPER_C)
        self.assertEqual(self.e.palette_mod,
                         [True, False], "C is the foreground")
        self.tap(organelle.UPPER_D)
        self.assertEqual(self.e.palette_mod, [True, True])
        self.tap(organelle.UPPER_C)
        self.assertEqual(self.e.palette_mod, [False, True])
        self.tap(organelle.UPPER_D)
        self.assertEqual(self.e.palette_mod, [False, False])

    def test_switching_on_moves_straight_away(self):
        # a key that does nothing visible for half a minute looks broken
        self.e.fg_palette = 3
        self.tap(organelle.UPPER_C)
        self.assertNotEqual(self.e.fg_palette, 3)

    def test_switching_off_leaves_the_palette_where_it_is(self):
        self.tap(organelle.UPPER_C)
        landed = self.e.fg_palette
        self.tap(organelle.UPPER_C)
        self.assertEqual(self.e.fg_palette, landed)

    def test_one_palette_does_not_disturb_the_other(self):
        self.e.bg_palette = 5
        self.tap(organelle.UPPER_C)
        self.assertEqual(self.e.bg_palette, 5)

    # --- the clock --------------------------------------------------------

    def test_nothing_moves_before_the_cycle_is_up(self):
        self.tap(organelle.UPPER_C)
        landed = self.e.fg_palette
        self.e.update_palette_mod()
        self.assertEqual(self.e.fg_palette, landed)

    def test_it_moves_once_the_cycle_is_up(self):
        self.tap(organelle.UPPER_C)
        landed = self.e.fg_palette
        self.e.palette_mod_next[self.e.PALETTE_FG] = 0    # long past
        self.e.update_palette_mod()
        self.assertNotEqual(self.e.fg_palette, landed)

    def test_the_cycle_comes_from_auto_random_cycle(self):
        import time
        self.e.config["auto_random_interval"] = 50
        before = time.time()
        self.e.arm_palette_mod(self.e.PALETTE_FG)
        due = self.e.palette_mod_next[self.e.PALETTE_FG] - before
        self.assertGreater(due, 49)
        self.assertLess(due, 51)

    def test_a_random_interval_stays_inside_its_range(self):
        self.e.config["auto_random_interval"] = -1
        import time
        for _ in range(20):
            before = time.time()
            self.e.arm_palette_mod(self.e.PALETTE_BG)
            due = self.e.palette_mod_next[self.e.PALETTE_BG] - before
            self.assertGreaterEqual(due, self.e.AUTO_RANDOM_MIN - 1)
            self.assertLessEqual(due, self.e.AUTO_RANDOM_MAX + 1)

    def test_the_two_palettes_keep_their_own_clocks(self):
        self.tap(organelle.UPPER_C)
        self.tap(organelle.UPPER_D)
        self.e.palette_mod_next[self.e.PALETTE_FG] = 0
        bg_was = self.e.bg_palette
        fg_was = self.e.fg_palette
        self.e.update_palette_mod()
        self.assertNotEqual(self.e.fg_palette, fg_was)
        self.assertEqual(self.e.bg_palette, bg_was, "bg was not due yet")

    def test_it_does_not_need_the_mode_picker_switched_on(self):
        # it borrows the interval, not the feature
        self.assertEqual(self.e.auto_random, self.e.AUTO_RANDOM_OFF)
        self.tap(organelle.UPPER_C)
        self.e.palette_mod_next[self.e.PALETTE_FG] = 0
        was = self.e.fg_palette
        self.e.update_palette_mod()
        self.assertNotEqual(self.e.fg_palette, was)

    def test_it_holds_still_in_a_menu(self):
        self.tap(organelle.UPPER_C)
        was = self.e.fg_palette
        self.e.palette_mod_next[self.e.PALETTE_FG] = 0
        self.e.menu_mode = True
        self.e.update_palette_mod()
        self.assertEqual(self.e.fg_palette, was)

    def test_the_key_does_nothing_in_a_menu(self):
        self.e.menu_mode = True
        self.tap(organelle.UPPER_C)
        self.assertEqual(self.e.palette_mod, [False, False])

    # --- picking ----------------------------------------------------------

    def test_it_never_picks_the_palette_already_showing(self):
        self.e.fg_palette = 4
        for _ in range(50):
            before = self.e.fg_palette
            self.e.pick_random_palette(self.e.PALETTE_FG)
            self.assertNotEqual(self.e.fg_palette, before)

    def test_one_palette_in_the_file_is_not_an_infinite_loop(self):
        self.e.palettes = ["only"]
        self.e.fg_palette = 0
        self.assertFalse(self.e.pick_random_palette(self.e.PALETTE_FG))
        self.assertEqual(self.e.fg_palette, 0)

    def test_it_stays_inside_the_palette_list(self):
        for _ in range(100):
            self.e.pick_random_palette(self.e.PALETTE_BG)
            self.assertTrue(0 <= self.e.bg_palette < len(self.e.palettes))

    # --- scenes -----------------------------------------------------------

    def test_a_scene_carries_the_wobble(self):
        self.tap(organelle.UPPER_D)
        fields = self.e._scene_fields()
        self.assertEqual(fields["palette_mod"], {"fg": False, "bg": True})

    def test_recalling_puts_it_back(self):
        self.e.apply_scene_palette_mod({"fg": True, "bg": False})
        self.assertEqual(self.e.palette_mod, [True, False])

    def test_a_scene_from_before_this_existed_loads_with_it_off(self):
        self.e.palette_mod = [True, True]
        for missing in (None, {}, "nonsense", [], {"fg": "yes"}):
            self.e.apply_scene_palette_mod(missing)
            self.assertEqual(self.e.palette_mod, [False, False],
                             f"from {missing!r}")

    def test_recalling_gives_it_a_full_cycle_before_it_moves(self):
        # otherwise it inherits whatever was left on the clock and can change
        # the moment the scene lands, throwing away the palette just recalled
        import time
        self.e.apply_scene_palette_mod({"fg": True, "bg": True})
        for which in (self.e.PALETTE_FG, self.e.PALETTE_BG):
            self.assertGreater(self.e.palette_mod_next[which], time.time() + 1)


class MidiChannelKeyTest(Base):

    def test_it_steps_on_the_way_up_not_the_way_down(self):
        organelle.dispatch_key(self.e, organelle.UPPER_E, 100)
        self.assertEqual(self.e.config["midi_channel"], 1, "not on press")
        organelle.dispatch_key(self.e, organelle.UPPER_E, 0)
        self.assertEqual(self.e.config["midi_channel"], 2)

    def test_holding_it_does_not_run_away(self):
        organelle.dispatch_key(self.e, organelle.UPPER_E, 100)
        for _ in range(120):
            self.e.update_key_repeater()
        self.assertEqual(self.e.config["midi_channel"], 1)
        organelle.dispatch_key(self.e, organelle.UPPER_E, 0)
        self.assertEqual(self.e.config["midi_channel"], 2, "one press, one step")

    def test_it_wraps_at_sixteen(self):
        self.e.config["midi_channel"] = 16
        self.tap(organelle.UPPER_E)
        self.assertEqual(self.e.config["midi_channel"], 1)

    def test_it_walks_the_whole_range(self):
        seen = []
        for _ in range(16):
            self.tap(organelle.UPPER_E)
            seen.append(self.e.config["midi_channel"])
        self.assertEqual(sorted(seen), list(range(1, 17)))

    def test_each_step_is_saved(self):
        self.tap(organelle.UPPER_E)
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.saved[-1]["midi_channel"], 2)

    def test_it_works_in_a_menu_too(self):
        # it is a setting, and the MIDI page is where you would be looking
        self.e.menu_mode = True
        self.tap(organelle.UPPER_E)
        self.assertEqual(self.e.config["midi_channel"], 2)


class OledFlagsTest(Base):
    """What the MOD page draws its lamps from."""

    def flags(self):
        sent = []
        oled.enabled = True
        oled.osc = types.SimpleNamespace(send=lambda *a: sent.append(a))
        oled._last_state = 0.0
        try:
            oled.update(self.e)
        finally:
            oled.enabled = False
        state = [m for m in sent if m[0] == "/oled/state"][-1]
        return state[9]     # the flags field, address plus eight ints before it

    def test_the_lamps_follow_the_keys(self):
        self.assertFalse(self.flags() & oled.FLAG_PAL_MOD_FG)
        self.assertFalse(self.flags() & oled.FLAG_PAL_MOD_BG)

        self.tap(organelle.UPPER_C)
        self.assertTrue(self.flags() & oled.FLAG_PAL_MOD_FG)
        self.assertFalse(self.flags() & oled.FLAG_PAL_MOD_BG)

        self.tap(organelle.UPPER_D)
        self.assertTrue(self.flags() & oled.FLAG_PAL_MOD_BG)

    def test_the_new_bits_do_not_land_on_an_old_one(self):
        # FLAG_KNOB_MOD is the base of a run of five rather than a flag of its
        # own, so it is expanded here instead of being counted once
        used = [v for k, v in vars(oled).items()
                if k.startswith("FLAG_") and k != "FLAG_KNOB_MOD"
                and isinstance(v, int)]
        used += [oled.FLAG_KNOB_MOD << i for i in range(5)]
        self.assertEqual(len(used), len(set(used)), "two flags share a bit")
        for v in used:
            self.assertEqual(v & (v - 1), 0, f"{v} is not a single bit")


if __name__ == "__main__":
    unittest.main(verbosity=2)
