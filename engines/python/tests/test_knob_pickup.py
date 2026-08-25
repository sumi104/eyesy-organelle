#!/usr/bin/env python3
"""Taking over a knob that another setting has already moved.

One knob, several settings sharing it. Found on the instrument: set modulation
rate at the far right, then hold the black key to change that knob's depth, and
the depth was dragged to the far right the moment the knob twitched. The two
could not be set independently, and neither could be nudged once set.

    python3 tests/test_knob_pickup.py
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

import audio_thru                    # noqa: E402
import eyesy as eyesy_module         # noqa: E402
import oled                          # noqa: E402


class Base(unittest.TestCase):

    def setUp(self):
        oled.enabled = False
        self.e = eyesy_module.Eyesy()
        self.e.config = dict(self.e.DEFAULT_CONFIG)
        self.e.mode_names = ["Alpha"]
        self.e.set_mode_by_index(0)
        self.e.save_config_file = lambda: None
        self.shown = []
        oled.notify_value = lambda label, v: self.shown.append((label, v))

    def tearDown(self):
        import importlib
        importlib.reload(oled)


class PickupRuleTest(Base):
    """knob_reaches(), which the three takeover sites share."""

    def test_it_grabs_when_the_knob_is_already_there(self):
        self.assertTrue(self.e.knob_reaches(0.5, 0.5, 0.5))

    def test_it_grabs_within_the_tolerance(self):
        tol = self.e.KNOB_PICKUP_TOLERANCE
        self.assertTrue(self.e.knob_reaches(0.5 + tol / 2, 1.0, 0.5))
        self.assertFalse(self.e.knob_reaches(0.5 + tol * 3, 1.0, 0.5))

    def test_it_grabs_on_the_way_past(self):
        # started above the value, now below it
        self.assertTrue(self.e.knob_reaches(0.1, 1.0, 0.5))
        # started below, now above
        self.assertTrue(self.e.knob_reaches(0.9, 0.0, 0.5))

    def test_it_does_not_grab_while_still_on_the_same_side(self):
        self.assertFalse(self.e.knob_reaches(0.8, 1.0, 0.5))
        self.assertFalse(self.e.knob_reaches(0.2, 0.0, 0.5))

    def test_a_value_at_the_end_of_the_travel_can_still_be_reached(self):
        # nothing is beyond 1.0 to cross from, so the tolerance is what grabs it
        self.assertTrue(self.e.knob_reaches(1.0, 0.0, 1.0))
        self.assertTrue(self.e.knob_reaches(0.0, 1.0, 0.0))


class KnobModulationTest(Base):

    def setUp(self):
        super().setUp()
        self.k = 0
        self.e.toggle_knob_mod(self.k)
        self.e.knob_hardware[self.k] = 0.20

    def turn(self, v):
        self.e.knob_hardware[self.k] = v
        self.e.update_knob_mod_control(self.k)

    def hold_key(self, held):
        self.e.knob_mod_key_held[self.k] = held

    def rate_at(self, pos):
        span = self.e.KNOB_MOD_RATE_MAX / self.e.KNOB_MOD_RATE_MIN
        return self.e.KNOB_MOD_RATE_MIN * (span ** pos)

    # --- the report -------------------------------------------------------

    def test_depth_is_not_dragged_to_where_the_rate_was_set(self):
        for v in (0.4, 0.7, 1.0):
            self.turn(v)
        self.assertAlmostEqual(self.e.knob_mod_rate[self.k],
                               self.e.KNOB_MOD_RATE_MAX)
        depth = self.e.knob_mod_depth[self.k]

        self.hold_key(True)
        self.turn(1.0)          # the switch to depth
        self.turn(0.94)         # this used to take depth with it
        self.assertEqual(self.e.knob_mod_depth[self.k], depth)
        self.turn(0.60)
        self.assertEqual(self.e.knob_mod_depth[self.k], depth)

    def test_it_takes_over_when_the_knob_reaches_the_depth(self):
        self.turn(1.0)
        self.hold_key(True)
        self.turn(1.0)
        depth = self.e.knob_mod_depth[self.k]

        self.turn(depth)        # arrives at it
        self.turn(0.05)         # and carries on
        self.assertAlmostEqual(self.e.knob_mod_depth[self.k], 0.05)

    def test_the_two_end_up_independent(self):
        # the whole point: a fast modulation that only moves a little
        for v in (0.5, 1.0):
            self.turn(v)
        self.hold_key(True)
        self.turn(1.0)
        for v in (0.7, 0.4, 0.25, 0.10):
            self.turn(v)
        self.assertAlmostEqual(self.e.knob_mod_rate[self.k],
                               self.e.KNOB_MOD_RATE_MAX, places=6)
        self.assertAlmostEqual(self.e.knob_mod_depth[self.k], 0.10)

    def test_going_back_to_the_rate_has_to_be_picked_up_too(self):
        # the first turn only says which of the two the knob is aimed at, so
        # it takes a sweep to actually put the rate at the top
        for v in (0.4, 0.7, 1.0):
            self.turn(v)
        self.assertAlmostEqual(self.e.knob_mod_rate[self.k],
                               self.e.KNOB_MOD_RATE_MAX)
        self.hold_key(True)
        self.turn(1.0)
        self.turn(0.20)                      # sweep down, grabs depth
        self.hold_key(False)
        self.turn(0.20)                      # back to rate, captures here
        self.turn(0.30)
        self.assertAlmostEqual(self.e.knob_mod_rate[self.k],
                               self.e.KNOB_MOD_RATE_MAX, places=6,
                               msg="rate must not follow until reached")

    # --- what the display says --------------------------------------------

    def test_the_value_being_hunted_for_is_shown(self):
        self.turn(1.0)
        depth = self.e.knob_mod_depth[self.k]
        self.shown.clear()
        self.hold_key(True)
        self.turn(1.0)
        self.assertEqual(self.shown[-1], ("Depth 1", depth),
                         "the target, so there is something to aim at")
        self.turn(0.8)
        self.assertEqual(self.shown[-1], ("Depth 1", depth))

    def test_once_grabbed_it_shows_where_the_knob_is(self):
        self.turn(1.0)
        self.hold_key(True)
        self.turn(1.0)
        self.turn(self.e.knob_mod_depth[self.k])
        self.shown.clear()
        self.turn(0.12)
        self.assertEqual(self.shown[-1], ("Depth 1", 0.12))

    # --- the rate's exponential ------------------------------------------

    def test_the_rate_position_is_the_inverse_of_the_curve(self):
        for pos in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0):
            self.e.knob_mod_rate[self.k] = self.rate_at(pos)
            self.assertAlmostEqual(self.e.knob_mod_rate_position(self.k), pos,
                                   places=9, msg=f"at {pos}")

    def test_the_position_stays_inside_the_travel(self):
        for rate in (0.0, 0.001, 0.02, 0.5, 5.0):
            self.e.knob_mod_rate[self.k] = rate
            p = self.e.knob_mod_rate_position(self.k)
            self.assertGreaterEqual(p, 0.0)
            self.assertLessEqual(p, 1.0)


class GainAndThruTest(Base):
    """Shift and knob 1, shift and knob 5. The same problem, the same rule."""

    def press_shift(self):
        self.e.dispatch_key_event(2, 100)

    def test_the_gain_is_not_dragged_to_where_the_knob_was_left(self):
        self.e.config["audio_gain"] = 0.25
        self.e.knob_hardware[0] = 1.0        # knob 1 left at the top by a mode
        self.press_shift()

        self.e.knob_hardware[0] = 0.90
        self.e.check_gain_knob()
        self.assertEqual(self.e.config["audio_gain"], 0.25)

        self.e.knob_hardware[0] = 0.25       # reaches it
        self.e.check_gain_knob()
        self.e.knob_hardware[0] = 0.40
        self.e.check_gain_knob()
        self.assertAlmostEqual(self.e.config["audio_gain"], 0.40)

    def test_the_gain_shows_what_it_is_hunting_for(self):
        self.e.config["audio_gain"] = 0.25
        self.e.knob_hardware[0] = 1.0
        self.press_shift()
        self.e.knob_hardware[0] = 0.90
        self.e.check_gain_knob()
        self.assertEqual(self.shown[-1], ("Input Gain", 0.25))

    def test_the_thru_level_is_not_dragged_either(self):
        audio_thru.enabled = False
        self.e.config["audio_thru_volume"] = 0.30
        self.e.knob_hardware[4] = 1.0
        self.press_shift()

        self.e.knob_hardware[4] = 0.90
        self.e.check_thru_knob()
        self.assertEqual(self.e.config["audio_thru_volume"], 0.30)

        self.e.knob_hardware[4] = 0.30
        self.e.check_thru_knob()
        self.e.knob_hardware[4] = 0.55
        self.e.check_thru_knob()
        self.assertAlmostEqual(self.e.config["audio_thru_volume"], 0.55)

    def test_a_still_knob_says_nothing(self):
        self.e.knob_hardware[0] = 0.5
        self.press_shift()
        self.e.knob_hardware[0] = 0.5
        for _ in range(60):
            self.e.check_gain_knob()
        self.assertEqual(self.shown, [], "sixty frames, nothing moved")


class SceneRecallTest(Base):
    """Recalling a scene must not put a Rate indicator on screen.

    Found on the instrument: with knob 5 modulating, the lower octave E, F
    and G each raised "Rate 5". They are scene minus, scene plus and save,
    and save ends in a recall of its own, so all three land on the same
    place -- a scene sets every knob's rate and depth, and clearing the edit
    state to None afterwards read to the next frame as the knob having just
    changed job, which is a thing worth saying on screen. It was not one
    anybody had asked for.
    """

    def setUp(self):
        super().setUp()
        self.e.scenes = []
        self.e.knob_mod = [False] * 5
        for k in range(5):
            self.e.knob_hardware[k] = 0.5

    def scene(self, on):
        return [{"on": bool(on[i]), "rate": 0.2, "depth": 0.3}
                for i in range(5)]

    def frames(self, n=3):
        for _ in range(n):
            self.e.update_knobs_and_notes()

    def test_a_recalled_scene_says_nothing_about_the_rate(self):
        self.e.apply_scene_knob_mod(self.scene([0, 0, 0, 0, 1]))
        self.shown.clear()
        self.frames()
        self.assertEqual(self.shown, [])

    def test_it_says_nothing_for_any_of_the_five(self):
        self.e.apply_scene_knob_mod(self.scene([1] * 5))
        self.shown.clear()
        self.frames()
        self.assertEqual(self.shown, [])

    def test_the_knob_still_has_to_be_picked_up_after_one(self):
        # quiet, but not trusting: the scene set the rate, so where the knob
        # happens to be sitting means nothing until it is brought to it
        self.e.apply_scene_knob_mod(self.scene([1, 0, 0, 0, 0]))
        rate = self.e.knob_mod_rate[0]
        target = self.e.knob_mod_rate_position(0)
        self.frames()
        # towards the rate's position but not as far as it, so it must not
        # take over. Going past it would be a pickup, and correctly so
        self.assertLess(0.60, target)
        self.e.knob_hardware[0] = 0.60
        self.frames()
        self.assertAlmostEqual(self.e.knob_mod_rate[0], rate,
                               msg="a scene's rate must not follow the knob"
                                   " until the knob reaches it")

    def test_the_key_still_says_so_when_it_is_the_key_asking(self):
        # the notification itself is wanted, just not from a scene change
        self.e.apply_scene_knob_mod(self.scene([0, 0, 0, 0, 1]))
        self.frames()
        self.shown.clear()
        self.e.knob_mod_key_held[4] = True
        self.frames(1)
        self.assertEqual(len(self.shown), 1)
        self.assertEqual(self.shown[0][0], "Depth 5")


if __name__ == "__main__":
    unittest.main(verbosity=2)
