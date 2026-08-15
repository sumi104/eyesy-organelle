#!/usr/bin/env python3
"""Checks the A# auto picker and the screen that sets its interval.

    python3 tests/test_auto_random.py
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
import screen_key_modes as skm      # noqa: E402


class AutoRandomTest(unittest.TestCase):

    def setUp(self):
        oled.enabled = False
        self.e = eyesy_module.Eyesy()
        self.e.config = dict(self.e.DEFAULT_CONFIG)
        self.e.mode_names = ["Alpha", "Beta", "Gamma", "Delta"]
        self.e.set_mode_by_index(0)
        self.e.scenes = []
        self.e.switch_menu_screen = lambda name: None
        self.e.save_config_file = lambda: None
        # recall_scene needs files, and where it lands is all this cares about
        self.recalled = []
        self.e.recall_scene = lambda i: self.recalled.append(i)

    def tap_a_sharp(self):
        organelle.dispatch_key(self.e, organelle.KEY_AS, 100)
        organelle.dispatch_key(self.e, organelle.KEY_AS, 0)

    # --- the key ---------------------------------------------------------

    def test_a_sharp_cycles_off_modes_scenes_off(self):
        self.assertEqual(self.e.auto_random, self.e.AUTO_RANDOM_OFF)
        self.tap_a_sharp()
        self.assertEqual(self.e.auto_random, self.e.AUTO_RANDOM_MODES)
        self.tap_a_sharp()
        self.assertEqual(self.e.auto_random, self.e.AUTO_RANDOM_SCENES)
        self.tap_a_sharp()
        self.assertEqual(self.e.auto_random, self.e.AUTO_RANDOM_OFF)

    def test_switching_it_on_picks_something_straight_away(self):
        # otherwise the key looks like it did nothing for up to a minute
        self.tap_a_sharp()
        self.assertNotEqual(self.e.mode, "Alpha")

    def test_it_never_picks_what_is_already_playing(self):
        self.e.auto_random = self.e.AUTO_RANDOM_MODES
        for _ in range(40):
            before = self.e.mode
            self.e.pick_random()
            self.assertNotEqual(self.e.mode, before)

    def test_one_mode_is_left_alone_rather_than_thrashing(self):
        self.e.mode_names = ["Only"]
        self.e.set_mode_by_index(0)
        self.e.auto_random = self.e.AUTO_RANDOM_MODES
        self.assertFalse(self.e.pick_random())
        self.assertEqual(self.e.mode, "Only")

    def test_scenes_with_none_saved_does_not_blow_up(self):
        self.e.auto_random = self.e.AUTO_RANDOM_SCENES
        self.assertFalse(self.e.pick_random())
        self.assertEqual(self.recalled, [])

    def test_scenes_are_picked_when_there_are_some(self):
        self.e.scenes = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        self.e.scene_index = 1
        self.e.auto_random = self.e.AUTO_RANDOM_SCENES
        for _ in range(20):
            self.assertTrue(self.e.pick_random())
        self.assertTrue(all(i != 1 for i in self.recalled))

    # --- the timer -------------------------------------------------------

    def test_nothing_happens_while_it_is_off(self):
        self.e.auto_random_next = 0        # long overdue
        self.e.update_auto_random()
        self.assertEqual(self.e.mode, "Alpha")

    def test_it_waits_for_the_interval(self):
        self.tap_a_sharp()
        settled = self.e.mode
        for _ in range(100):
            self.e.update_auto_random()
        self.assertEqual(self.e.mode, settled, "should still be waiting")

    def test_it_moves_once_the_interval_is_up(self):
        self.tap_a_sharp()
        settled = self.e.mode
        self.e.auto_random_next = 0
        self.e.update_auto_random()
        self.assertNotEqual(self.e.mode, settled)

    def test_it_holds_still_while_a_menu_is_open(self):
        self.tap_a_sharp()
        settled = self.e.mode
        self.e.menu_mode = True
        self.e.auto_random_next = 0
        self.e.update_auto_random()
        self.assertEqual(self.e.mode, settled)

    def test_a_random_interval_stays_in_range(self):
        self.e.config["auto_random_interval"] = -1
        self.e.auto_random = self.e.AUTO_RANDOM_MODES
        import time
        for _ in range(50):
            self.e.arm_auto_random()
            wait = self.e.auto_random_next - time.time()
            self.assertGreaterEqual(wait, self.e.AUTO_RANDOM_MIN - 1)
            self.assertLessEqual(wait, self.e.AUTO_RANDOM_MAX + 1)

    def test_what_the_display_says(self):
        self.assertEqual(self.e.auto_random_text(), "off")
        self.e.auto_random = self.e.AUTO_RANDOM_MODES
        self.assertEqual(self.e.auto_random_text(), "modes every 30s")
        self.e.config["auto_random_interval"] = -1
        self.e.auto_random = self.e.AUTO_RANDOM_SCENES
        self.assertEqual(self.e.auto_random_text(), "scenes every random")
        for seconds in self.e.AUTO_RANDOM_INTERVALS:
            self.e.config["auto_random_interval"] = seconds
            self.assertLessEqual(len(self.e.auto_random_text()), 21)

    # --- the settings screen --------------------------------------------

    def test_the_interval_row_offers_every_choice(self):
        screen = skm.ScreenKeyModes(self.e)
        seen = []
        for value in range(0, len(self.e.AUTO_RANDOM_INTERVALS)):
            screen.interval_item.value = value
            screen._relabel(screen.interval_item)
            seen.append(screen.interval_item.text)
        self.assertEqual(seen, ["Auto Random Cycle: 15 sec",
                                "Auto Random Cycle: 30 sec",
                                "Auto Random Cycle: 50 sec",
                                "Auto Random Cycle: 60 sec",
                                "Auto Random Cycle: Random"])

    def test_the_interval_saves_as_seconds_not_as_a_row_number(self):
        screen = skm.ScreenKeyModes(self.e)
        screen.before()
        screen.interval_item.value = 3          # the 60 sec row
        screen.save()
        self.assertEqual(self.e.config["auto_random_interval"], 60)

        screen.before()
        self.assertEqual(screen.interval_item.value, 3, "and comes back")

    def test_the_mode_slots_still_line_up_under_the_new_row(self):
        self.e.key_modes[0] = "Gamma"
        self.e.key_modes[6] = "Beta"
        screen = skm.ScreenKeyModes(self.e)
        screen.before()
        self.assertIn("Gamma", screen.slot_items[0].text)
        self.assertIn("Beta", screen.slot_items[6].text)
        self.assertTrue(screen.slot_items[0].text.startswith("C "))
        self.assertTrue(screen.slot_items[6].text.startswith("B "))

        screen.slot_items[0].value = screen._mode_index("Delta")
        screen.save()
        self.assertEqual(self.e.key_modes[0], "Delta")
        self.assertEqual(self.e.key_modes[6], "Beta")

    def test_adjusting_respects_each_row_s_own_limits(self):
        screen = skm.ScreenKeyModes(self.e)
        screen.before()

        for _ in range(20):
            screen.menu_inc_value(screen.interval_item)
        self.assertEqual(screen.interval_item.value,
                         len(self.e.AUTO_RANDOM_INTERVALS) - 1)

        slot = screen.slot_items[0]
        for _ in range(20):
            screen.menu_inc_value(slot)
        self.assertEqual(slot.value, len(self.e.mode_names) - 1)
        for _ in range(20):
            screen.menu_dec_value(slot)
        self.assertEqual(slot.value, -1, "one below the first mode is None")


class LoopOrderTest(unittest.TestCase):
    """Where update_auto_random() sits in the main loop is the whole bug.

    It changes eyesy.mode and eyesy.mode_root. The loop binds the module to
    draw once per frame from eyesy.mode, so if the pick happens after that
    binding the frame calls the outgoing mode's draw() with the incoming
    mode's mode_root. Modes that only read knobs never notice. A mode that
    opens a file in draw(), "T - Font Recedes" loading font.ttf out of
    eyesy.mode_root, raises FileNotFoundError against a folder that has no
    such file.

    It has to land with the other inputs, before the knobs are read and
    before the module lookup.
    """

    def setUp(self):
        with open("main.py") as f:
            self.lines = f.read().splitlines()

    def line_of(self, needle, after=0):
        for i in range(after, len(self.lines)):
            stripped = self.lines[i].strip()
            if stripped.startswith("#"):
                continue
            if needle in stripped:
                return i
        self.fail(f"{needle!r} is gone from main.py")

    def test_the_pick_happens_before_the_module_to_draw_is_chosen(self):
        # the loop body, past the once-only setup that also binds a module
        loop = self.line_of("osc.recv()")
        pick = self.line_of("eyesy.update_auto_random()", loop)
        bind = self.line_of("mode = sys.modules[eyesy.mode]", loop)
        draw = self.line_of("mode.draw(mode_screen, eyesy)", loop)

        self.assertLess(pick, bind,
                        "a mode picked after this binding draws the old "
                        "module against the new mode_root")
        self.assertLess(bind, draw)

    def test_the_pick_happens_before_the_knobs_are_read(self):
        # recall_scene() writes eyesy.knob, set_knobs() is what hands those
        # to the mode. The other way round and a recalled scene is a frame late.
        loop = self.line_of("osc.recv()")
        pick = self.line_of("eyesy.update_auto_random()", loop)
        knobs = self.line_of("eyesy.set_knobs()", loop)
        self.assertLess(pick, knobs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
