#!/usr/bin/env python3
"""The upper octave white keys.

C and D step the foreground palette, E and F the background, and a pair
pressed together switches that palette's wobble. G steps the MIDI channel.

Two things here are easy to get wrong and are what most of this file is
about. The keys act on the way up, because on the way down a single key and
the first half of a chord look identical; and the wobble runs on the Auto
Random Cycle clock rather than on the trigger, unlike the knob wobble it
otherwise resembles.

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
        self.e.palettes = [{"name": f"Palette {i}"} for i in range(8)]

    def press(self, k):
        organelle.dispatch_key(self.e, k, 100)

    def release(self, k):
        organelle.dispatch_key(self.e, k, 0)

    def tap(self, k):
        self.press(k)
        self.release(k)

    def tick(self, n=1):
        """n frames of the main loop, as far as the keys are concerned."""
        for _ in range(n):
            self.e.update_key_repeater()

    def chord(self, a, b):
        """Both down, then both up, which is how a hand does it."""
        self.press(a)
        self.press(b)
        self.release(b)
        self.release(a)

    FG_DOWN, FG_UP = organelle.UPPER_C, organelle.UPPER_D
    BG_DOWN, BG_UP = organelle.UPPER_E, organelle.UPPER_F


class PaletteModTest(Base):

    def test_it_starts_off(self):
        self.assertEqual(self.e.palette_mod, [False, False])

    def test_each_pair_toggles_its_own_palette(self):
        self.chord(self.FG_DOWN, self.FG_UP)
        self.assertEqual(self.e.palette_mod,
                         [True, False], "C and D are the foreground")
        self.chord(self.BG_DOWN, self.BG_UP)
        self.assertEqual(self.e.palette_mod, [True, True])
        self.chord(self.FG_DOWN, self.FG_UP)
        self.assertEqual(self.e.palette_mod, [False, True])
        self.chord(self.BG_DOWN, self.BG_UP)
        self.assertEqual(self.e.palette_mod, [False, False])

    def test_switching_on_moves_straight_away(self):
        # a key that does nothing visible for half a minute looks broken
        self.e.fg_palette = 3
        self.chord(self.FG_DOWN, self.FG_UP)
        self.assertNotEqual(self.e.fg_palette, 3)

    def test_switching_off_leaves_the_palette_where_it_is(self):
        self.chord(self.FG_DOWN, self.FG_UP)
        landed = self.e.fg_palette
        self.chord(self.FG_DOWN, self.FG_UP)
        self.assertEqual(self.e.fg_palette, landed)

    def test_one_palette_does_not_disturb_the_other(self):
        self.e.bg_palette = 5
        self.chord(self.FG_DOWN, self.FG_UP)
        self.assertEqual(self.e.bg_palette, 5)

    # --- the clock --------------------------------------------------------

    def test_nothing_moves_before_the_cycle_is_up(self):
        self.chord(self.FG_DOWN, self.FG_UP)
        landed = self.e.fg_palette
        self.e.update_palette_mod()
        self.assertEqual(self.e.fg_palette, landed)

    def test_it_moves_once_the_cycle_is_up(self):
        self.chord(self.FG_DOWN, self.FG_UP)
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
        self.chord(self.FG_DOWN, self.FG_UP)
        self.chord(self.BG_DOWN, self.BG_UP)
        self.e.palette_mod_next[self.e.PALETTE_FG] = 0
        bg_was = self.e.bg_palette
        fg_was = self.e.fg_palette
        self.e.update_palette_mod()
        self.assertNotEqual(self.e.fg_palette, fg_was)
        self.assertEqual(self.e.bg_palette, bg_was, "bg was not due yet")

    def test_it_does_not_need_the_mode_picker_switched_on(self):
        # it borrows the interval, not the feature
        self.assertEqual(self.e.auto_random, self.e.AUTO_RANDOM_OFF)
        self.chord(self.FG_DOWN, self.FG_UP)
        self.e.palette_mod_next[self.e.PALETTE_FG] = 0
        was = self.e.fg_palette
        self.e.update_palette_mod()
        self.assertNotEqual(self.e.fg_palette, was)

    def test_it_holds_still_in_a_menu(self):
        self.chord(self.FG_DOWN, self.FG_UP)
        was = self.e.fg_palette
        self.e.palette_mod_next[self.e.PALETTE_FG] = 0
        self.e.menu_mode = True
        self.e.update_palette_mod()
        self.assertEqual(self.e.fg_palette, was)

    def test_the_chord_does_nothing_in_a_menu(self):
        self.e.menu_mode = True
        self.chord(self.FG_DOWN, self.FG_UP)
        self.assertEqual(self.e.palette_mod, [False, False])

    def test_a_chord_let_go_inside_a_menu_leaves_no_key_armed(self):
        # pressed while performing, released after something opened a menu.
        # the used flags have to be cleared or the next tap steps twice.
        self.press(self.FG_DOWN)
        self.press(self.FG_UP)
        self.e.menu_mode = True
        self.release(self.FG_UP)
        self.release(self.FG_DOWN)
        self.e.menu_mode = False
        self.assertEqual(self.e.palette_key_used, [False] * 4)
        self.assertEqual(self.e.palette_key_held, [False] * 4)

    # --- picking ----------------------------------------------------------

    def test_it_never_picks_the_palette_already_showing(self):
        self.e.fg_palette = 4
        for _ in range(50):
            before = self.e.fg_palette
            self.e.pick_random_palette(self.e.PALETTE_FG)
            self.assertNotEqual(self.e.fg_palette, before)

    def test_one_palette_in_the_file_is_not_an_infinite_loop(self):
        self.e.palettes = [{"name": "only"}]
        self.e.fg_palette = 0
        self.assertFalse(self.e.pick_random_palette(self.e.PALETTE_FG))
        self.assertEqual(self.e.fg_palette, 0)

    def test_it_stays_inside_the_palette_list(self):
        for _ in range(100):
            self.e.pick_random_palette(self.e.PALETTE_BG)
            self.assertTrue(0 <= self.e.bg_palette < len(self.e.palettes))

    # --- scenes -----------------------------------------------------------

    def test_a_scene_carries_the_wobble(self):
        self.chord(self.BG_DOWN, self.BG_UP)
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


class PaletteStepTest(Base):
    """A key on its own steps its palette."""

    def test_each_key_steps_its_own_palette_its_own_way(self):
        self.e.fg_palette = self.e.bg_palette = 3
        self.tap(self.FG_DOWN)
        self.assertEqual((self.e.fg_palette, self.e.bg_palette), (2, 3))
        self.tap(self.FG_UP)
        self.assertEqual((self.e.fg_palette, self.e.bg_palette), (3, 3))
        self.tap(self.BG_DOWN)
        self.assertEqual((self.e.fg_palette, self.e.bg_palette), (3, 2))
        self.tap(self.BG_UP)
        self.assertEqual((self.e.fg_palette, self.e.bg_palette), (3, 3))

    def test_it_steps_on_the_way_up_not_the_way_down(self):
        # the whole chord scheme rests on this
        self.e.fg_palette = 3
        self.press(self.FG_UP)
        self.assertEqual(self.e.fg_palette, 3, "nothing on the way down")
        self.release(self.FG_UP)
        self.assertEqual(self.e.fg_palette, 4)

    def test_it_wraps_at_both_ends(self):
        last = len(self.e.palettes) - 1
        self.e.fg_palette = last
        self.tap(self.FG_UP)
        self.assertEqual(self.e.fg_palette, 0)
        self.tap(self.FG_DOWN)
        self.assertEqual(self.e.fg_palette, last)

    def test_a_tap_is_still_one_step(self):
        self.e.fg_palette = 3
        self.press(self.FG_UP)
        self.tick(self.e.PALETTE_REPEAT_DELAY - 1)   # let go before it starts
        self.release(self.FG_UP)
        self.assertEqual(self.e.fg_palette, 4)

    def test_holding_starts_stepping_after_the_delay(self):
        self.e.fg_palette = 3
        self.press(self.FG_UP)
        self.tick(self.e.PALETTE_REPEAT_DELAY - 1)
        self.assertEqual(self.e.fg_palette, 3, "nothing yet")
        self.tick(1)
        self.assertEqual(self.e.fg_palette, 4, "the first of the run")

    def test_it_keeps_going_at_the_rate_it_is_set_to(self):
        self.e.fg_palette = 0
        self.press(self.FG_UP)
        self.tick(self.e.PALETTE_REPEAT_DELAY
                  + (self.e.PALETTE_REPEAT_EVERY * 5))
        self.assertEqual(self.e.fg_palette, 6, "one on the delay, five since")

    def test_letting_go_after_a_run_does_not_add_one_more(self):
        self.e.fg_palette = 0
        self.press(self.FG_UP)
        self.tick(self.e.PALETTE_REPEAT_DELAY)
        self.assertEqual(self.e.fg_palette, 1)
        self.release(self.FG_UP)
        self.assertEqual(self.e.fg_palette, 1)

    def test_the_other_direction_repeats_too(self):
        self.e.bg_palette = 5
        self.press(self.BG_DOWN)
        self.tick(self.e.PALETTE_REPEAT_DELAY + self.e.PALETTE_REPEAT_EVERY)
        self.release(self.BG_DOWN)
        self.assertEqual(self.e.bg_palette, 3)

    def test_it_does_not_repeat_in_a_menu(self):
        self.e.fg_palette = 3
        self.press(self.FG_UP)
        self.e.menu_mode = True
        self.tick(120)
        self.assertEqual(self.e.fg_palette, 3)

    def test_a_key_that_is_not_held_does_not_tick(self):
        self.e.fg_palette = 3
        self.tick(120)
        self.assertEqual(self.e.fg_palette, 3)

    def test_nothing_steps_in_a_menu(self):
        self.e.fg_palette = 3
        self.e.menu_mode = True
        self.tap(self.FG_UP)
        self.assertEqual(self.e.fg_palette, 3)

    def test_the_spare_keys_do_nothing(self):
        before = (self.e.fg_palette, self.e.bg_palette,
                  self.e.config["midi_channel"], list(self.e.palette_mod))
        for k in (organelle.UPPER_A, organelle.UPPER_B):
            self.tap(k)
        self.assertEqual((self.e.fg_palette, self.e.bg_palette,
                          self.e.config["midi_channel"],
                          list(self.e.palette_mod)), before)


class PaletteChordTest(Base):
    """Two of a pair held together, instead of either of them alone."""

    def test_the_chord_does_not_also_step_the_palette(self):
        # the wobble picks a palette when it starts, so compare against what
        # the same chord does with the wobble already on and settling
        self.e.fg_palette = 3
        self.press(self.FG_DOWN)
        self.press(self.FG_UP)
        self.release(self.FG_UP)
        self.release(self.FG_DOWN)
        self.assertTrue(self.e.palette_mod[self.e.PALETTE_FG])
        # switching it off must leave the palette alone, not step it twice
        landed = self.e.fg_palette
        self.chord(self.FG_DOWN, self.FG_UP)
        self.assertFalse(self.e.palette_mod[self.e.PALETTE_FG])
        self.assertEqual(self.e.fg_palette, landed)

    def test_the_order_the_keys_go_down_does_not_matter(self):
        self.chord(self.FG_UP, self.FG_DOWN)
        self.assertTrue(self.e.palette_mod[self.e.PALETTE_FG])

    def test_the_order_the_keys_come_up_does_not_matter(self):
        self.e.fg_palette = 3
        self.press(self.FG_DOWN)
        self.press(self.FG_UP)
        self.release(self.FG_DOWN)      # the first one down comes up first
        self.release(self.FG_UP)
        self.assertTrue(self.e.palette_mod[self.e.PALETTE_FG])
        landed = self.e.fg_palette
        self.chord(self.FG_DOWN, self.FG_UP)
        self.assertEqual(self.e.fg_palette, landed, "neither key stepped")

    def test_one_after_the_other_is_two_steps_not_a_chord(self):
        self.e.fg_palette = 3
        self.tap(self.FG_DOWN)
        self.tap(self.FG_UP)
        self.assertEqual(self.e.fg_palette, 3, "down then up, back where it was")
        self.assertFalse(self.e.palette_mod[self.e.PALETTE_FG])

    def test_a_key_from_each_pair_is_not_a_chord(self):
        # C and E are adjacent white keys but belong to different palettes
        self.e.fg_palette = self.e.bg_palette = 3
        self.press(self.FG_DOWN)
        self.press(self.BG_DOWN)
        self.release(self.BG_DOWN)
        self.release(self.FG_DOWN)
        self.assertEqual(self.e.palette_mod, [False, False])
        self.assertEqual((self.e.fg_palette, self.e.bg_palette), (2, 2))

    def test_holding_one_and_tapping_the_other_twice_toggles_twice(self):
        self.press(self.FG_DOWN)
        self.press(self.FG_UP)
        self.release(self.FG_UP)
        self.assertTrue(self.e.palette_mod[self.e.PALETTE_FG])
        self.press(self.FG_UP)
        self.release(self.FG_UP)
        self.assertFalse(self.e.palette_mod[self.e.PALETTE_FG])
        self.release(self.FG_DOWN)
        self.assertEqual(self.e.palette_key_used, [False] * 4)

    def test_the_chord_still_reads_with_a_frame_or_two_between_presses(self):
        # two fingers are never exactly simultaneous
        self.press(self.FG_DOWN)
        self.tick(2)
        self.press(self.FG_UP)
        self.assertTrue(self.e.palette_mod[self.e.PALETTE_FG])

    def test_the_partner_of_a_repeating_key_is_not_a_chord(self):
        # somebody scrolling who presses the other key wants to go back the
        # other way, not to land on the wobble switch
        self.e.fg_palette = 0
        self.press(self.FG_UP)
        self.tick(self.e.PALETTE_REPEAT_DELAY)
        self.assertEqual(self.e.fg_palette, 1, "it is running")
        self.press(self.FG_DOWN)
        self.assertFalse(self.e.palette_mod[self.e.PALETTE_FG],
                         "must not have switched the wobble on")
        self.release(self.FG_DOWN)
        self.assertEqual(self.e.fg_palette, 0, "it stepped back instead")

    def test_a_held_chord_does_not_repeat(self):
        # a toggle that repeated would flip on and off many times a second
        self.press(self.FG_DOWN)
        self.press(self.FG_UP)
        on = self.e.palette_mod[self.e.PALETTE_FG]
        landed = self.e.fg_palette
        self.tick(120)
        self.assertEqual(self.e.palette_mod[self.e.PALETTE_FG], on)
        self.assertEqual(self.e.fg_palette, landed)

    def test_a_chord_leaves_nothing_armed_behind_it(self):
        self.chord(self.FG_DOWN, self.FG_UP)
        self.assertEqual(self.e.palette_key_held, [False] * 4)
        self.assertEqual(self.e.palette_key_used, [False] * 4)
        # and the next single tap steps exactly once
        self.e.fg_palette = 3
        self.tap(self.FG_UP)
        self.assertEqual(self.e.fg_palette, 4)


class MidiChannelKeyTest(Base):

    def test_it_steps_on_the_way_up_not_the_way_down(self):
        organelle.dispatch_key(self.e, organelle.UPPER_G, 100)
        self.assertEqual(self.e.config["midi_channel"], 1, "not on press")
        organelle.dispatch_key(self.e, organelle.UPPER_G, 0)
        self.assertEqual(self.e.config["midi_channel"], 2)

    def test_holding_it_does_not_run_away(self):
        organelle.dispatch_key(self.e, organelle.UPPER_G, 100)
        for _ in range(120):
            self.e.update_key_repeater()
        self.assertEqual(self.e.config["midi_channel"], 1)
        organelle.dispatch_key(self.e, organelle.UPPER_G, 0)
        self.assertEqual(self.e.config["midi_channel"], 2, "one press, one step")

    def test_it_wraps_at_sixteen(self):
        self.e.config["midi_channel"] = 16
        self.tap(organelle.UPPER_G)
        self.assertEqual(self.e.config["midi_channel"], 1)

    def test_it_walks_the_whole_range(self):
        seen = []
        for _ in range(16):
            self.tap(organelle.UPPER_G)
            seen.append(self.e.config["midi_channel"])
        self.assertEqual(sorted(seen), list(range(1, 17)))

    def test_each_step_is_saved(self):
        self.tap(organelle.UPPER_G)
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.saved[-1]["midi_channel"], 2)

    def test_it_works_in_a_menu_too(self):
        # it is a setting, and the MIDI page is where you would be looking
        self.e.menu_mode = True
        self.tap(organelle.UPPER_G)
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

        self.chord(self.FG_DOWN, self.FG_UP)
        self.assertTrue(self.flags() & oled.FLAG_PAL_MOD_FG)
        self.assertFalse(self.flags() & oled.FLAG_PAL_MOD_BG)

        self.chord(self.BG_DOWN, self.BG_UP)
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
