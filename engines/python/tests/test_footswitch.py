#!/usr/bin/env python3
"""Checks the pedal jack and the System menu row that picks what it does.

    python3 tests/test_footswitch.py
"""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.chdir(os.path.dirname(HERE))

# screen_flash_drive only offers the row on the instrument that has the jack,
# and this has to be set before organelle is imported anywhere
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

import eyesy as eyesy_module            # noqa: E402
import oled                             # noqa: E402
import organelle                        # noqa: E402
from screen_flash_drive import ScreenFlashDrive   # noqa: E402


class _Keys:
    """The menu reads these off eyesy, all of them, every frame."""

    NAMES = ["key4_press", "key4_status", "key5_press", "key5_status",
             "key6_press", "key6_status", "key7_press", "key7_status",
             "key8_press"]


class FootswitchKeyTest(unittest.TestCase):

    def setUp(self):
        oled.enabled = False
        self.e = eyesy_module.Eyesy()
        self.e.config = dict(self.e.DEFAULT_CONFIG)
        self.e.mode_names = ["Alpha", "Beta"]
        self.e.set_mode_by_index(0)
        self.e.scenes = []
        self.saved = []
        self.e.save_scene = lambda: self.saved.append(True)

    def press(self):
        organelle.dispatch_key(self.e, organelle.FOOTSWITCH, 100)

    def release(self):
        organelle.dispatch_key(self.e, organelle.FOOTSWITCH, 0)

    # --- save scene, which is what it did before there was a choice --------

    def test_it_saves_by_default(self):
        self.assertEqual(self.e.config["footswitch"], self.e.FOOTSWITCH_SAVE)
        self.press()
        self.assertEqual(len(self.saved), 1)
        self.assertFalse(self.e.trig)

    def test_saving_happens_once_per_press_not_on_release(self):
        self.press()
        self.release()
        self.assertEqual(len(self.saved), 1)

    # --- trigger ----------------------------------------------------------

    def test_it_triggers_when_set_to(self):
        self.e.config["footswitch"] = self.e.FOOTSWITCH_TRIGGER
        self.press()
        self.assertTrue(self.e.trig)
        self.assertEqual(self.saved, [], "and does not also save")

    def test_the_trigger_lasts_one_frame_like_every_other_source(self):
        self.e.config["footswitch"] = self.e.FOOTSWITCH_TRIGGER
        self.press()
        self.e.clear_flags()
        self.assertFalse(self.e.trig)

    def test_releasing_does_not_trigger(self):
        # otherwise one stomp reads as two
        self.e.config["footswitch"] = self.e.FOOTSWITCH_TRIGGER
        self.press()
        self.e.clear_flags()
        self.release()
        self.assertFalse(self.e.trig)

    # --- it is the panel trigger key, not a copy of half of it ------------

    def test_holding_it_plays_the_test_tone_the_panel_key_plays(self):
        # key10_status is what makes main.py feed the modes a sine wave
        # instead of the live input, same as holding B on the keyboard
        self.e.config["footswitch"] = self.e.FOOTSWITCH_TRIGGER
        self.press()
        self.assertTrue(self.e.key10_status)
        self.release()
        self.assertFalse(self.e.key10_status)

    def test_shift_and_the_pedal_arm_the_knob_sequencer(self):
        self.e.config["footswitch"] = self.e.FOOTSWITCH_TRIGGER
        self.e.key2_status = True
        self.press()
        self.assertEqual(self.e.knob_seq_state, "enabled")
        self.assertFalse(self.e.trig, "the shifted meaning replaces it")

    def test_shift_and_the_pedal_again_disarm_it(self):
        self.e.config["footswitch"] = self.e.FOOTSWITCH_TRIGGER
        self.e.key2_status = True
        self.press()
        self.release()
        self.press()
        self.assertEqual(self.e.knob_seq_state, "stopped")

    def test_arming_does_not_start_the_test_tone(self):
        # it goes nowhere near key 10, which is what plays it
        self.e.config["footswitch"] = self.e.FOOTSWITCH_TRIGGER
        self.e.key2_status = True
        self.press()
        self.assertFalse(self.e.key10_status)

    def test_arming_does_nothing_with_a_menu_open(self):
        self.e.config["footswitch"] = self.e.FOOTSWITCH_TRIGGER
        self.e.key2_status = True
        self.e.menu_mode = True
        self.press()
        self.assertEqual(self.e.knob_seq_state, "stopped")

    # --- and no repeat off the pedal --------------------------------------

    def repeat_frames(self, n=40):
        fired = 0
        for _ in range(n):
            self.e.update_key_repeater()
            if self.e.trig:
                fired += 1
            self.e.clear_flags()
        return fired

    def test_shift_and_a_held_pedal_do_not_machine_gun_the_trigger(self):
        # the repeat lives in the unshifted branch of update_key_repeater, so
        # reaching for shift with the pedal already down stops it rather than
        # starting it. Worth pinning: it reads the other way round.
        self.e.config["footswitch"] = self.e.FOOTSWITCH_TRIGGER
        self.press()                    # down first, unshifted
        self.e.clear_flags()
        self.e.key2_status = True       # then shift, with the pedal still down
        self.assertEqual(self.repeat_frames(), 0)

    def test_holding_the_pedal_repeats_exactly_as_holding_b_does(self):
        self.e.config["footswitch"] = self.e.FOOTSWITCH_TRIGGER
        self.press()
        self.e.clear_flags()
        by_pedal = self.repeat_frames()

        self.release()
        self.e.key10_td = 0
        self.e.dispatch_key_event(organelle.EYESY_TRIGGER_BUTTON, 100)
        self.e.clear_flags()
        by_key = self.repeat_frames()

        self.assertGreater(by_pedal, 0)
        self.assertEqual(by_pedal, by_key)

    def test_the_pedal_reports_itself_held_whatever_it_is_set_to(self):
        for action in (self.e.FOOTSWITCH_SAVE, self.e.FOOTSWITCH_TRIGGER):
            self.e.config["footswitch"] = action
            self.press()
            self.assertTrue(self.e.footswitch_status)
            self.release()
            self.assertFalse(self.e.footswitch_status)

    def test_switching_the_setting_mid_press_does_not_strand_the_tone(self):
        # the release would go to the save branch and leave key10_status on,
        # with the analysis input stuck at a sine wave
        self.e.config["footswitch"] = self.e.FOOTSWITCH_TRIGGER
        self.press()
        self.e.config["footswitch"] = self.e.FOOTSWITCH_SAVE
        self.release()
        self.assertFalse(self.e.key10_status)
        self.assertEqual(self.saved, [], "and does not save on that release")

    def test_the_other_way_round_is_not_stranded_either(self):
        self.e.config["footswitch"] = self.e.FOOTSWITCH_SAVE
        self.press()
        self.e.config["footswitch"] = self.e.FOOTSWITCH_TRIGGER
        self.release()
        self.assertFalse(self.e.key10_status)
        self.assertEqual(len(self.saved), 1, "the press is what saved")

    # --- both -------------------------------------------------------------

    def test_saving_does_not_fire_with_a_menu_open(self):
        self.e.config["footswitch"] = self.e.FOOTSWITCH_SAVE
        self.e.menu_mode = True
        self.press()
        self.assertEqual(self.saved, [])

    def test_the_trigger_does_not_fire_with_a_menu_open(self):
        # dispatch_key_event routes key 10 to menu navigation there, the same
        # as the panel key, so nothing triggers behind the menu
        self.e.config["footswitch"] = self.e.FOOTSWITCH_TRIGGER
        self.e.menu_mode = True
        self.press()
        self.assertFalse(self.e.trig)

    # --- what the display says --------------------------------------------

    def oled_flags(self):
        """The flags field of the next /oled/state, as the display sees it."""
        sent = []

        class _Osc:
            def send(self, address, *args):
                if address == "/oled/state":
                    sent.append(args)

        was, oled.osc, oled.enabled = oled.osc, _Osc(), True
        oled._last_state = 0.0
        try:
            oled.update(self.e)
        finally:
            oled.osc, oled.enabled = was, False
        self.assertTrue(sent, "no state went out")
        return sent[-1][8]        # the field main.cpp reads into st.flags

    def test_arming_lights_the_sequencer_letter(self):
        # it used to sit armed with nothing on screen to say so, so the only
        # sign the key had worked was a knob starting a recording
        self.e.config["footswitch"] = self.e.FOOTSWITCH_TRIGGER
        self.e.key2_status = True
        self.press()
        self.assertEqual(self.e.knob_seq_state, "enabled")
        self.assertTrue(self.oled_flags() & oled.FLAG_SEQ_ARM)

    def test_each_sequencer_state_lights_one_letter_and_no_other(self):
        # the three share a single slot in the top bar
        wanted = {"stopped": 0,
                  "enabled": oled.FLAG_SEQ_ARM,
                  "recording": oled.FLAG_SEQ_REC,
                  "playing": oled.FLAG_SEQ_PLAY}
        every = oled.FLAG_SEQ_ARM | oled.FLAG_SEQ_REC | oled.FLAG_SEQ_PLAY
        for state, bit in wanted.items():
            self.e.knob_seq_state = state
            self.assertEqual(self.oled_flags() & every, bit, state)

    # --- the stored value -------------------------------------------------

    def test_a_junk_value_falls_back_rather_than_picking_nothing(self):
        for junk in (99, -1, "trigger", None):
            self.e.config["footswitch"] = junk
            self.e.validate_config()
            self.assertIn(self.e.config["footswitch"],
                          range(len(self.e.FOOTSWITCH_ACTIONS)))

    def test_a_good_value_survives_validation(self):
        self.e.config["footswitch"] = self.e.FOOTSWITCH_TRIGGER
        self.e.validate_config()
        self.assertEqual(self.e.config["footswitch"], self.e.FOOTSWITCH_TRIGGER)


class SystemScreenTest(unittest.TestCase):

    def setUp(self):
        oled.enabled = False
        self.e = eyesy_module.Eyesy()
        self.e.config = dict(self.e.DEFAULT_CONFIG)
        self.e.switch_menu_screen = lambda name: None
        self.written = []
        self.e.save_config_file = lambda: self.written.append(
            self.e.config["footswitch"])

        for name in _Keys.NAMES:
            setattr(self.e, name, False)
        self.e.key10_status = False
        self.e.footswitch_status = False

        self.screen = ScreenFlashDrive(self.e)
        self.screen.ensure_usb_mounted = lambda: True   # no lsblk in a test
        self.screen.before()

    def item(self):
        return self.screen.footswitch_item

    def select_footswitch(self):
        self.screen.menu.selected_index = self.screen.menu.items.index(self.item())

    def frame(self, **keys):
        for name in _Keys.NAMES:
            setattr(self.e, name, keys.get(name, False))
        self.screen.handle_events()

    # --- the row ----------------------------------------------------------

    def test_the_row_is_there_and_reads_the_stored_value(self):
        self.assertEqual(self.item().text, "Foot Switch: Save Scene")

    def test_it_shows_whatever_was_stored(self):
        self.e.config["footswitch"] = self.e.FOOTSWITCH_TRIGGER
        self.screen.before()
        self.assertEqual(self.item().text, "Foot Switch: Trigger")

    def test_exit_is_under_the_cursor_on_the_way_in(self):
        # a menu that opens on Backup or Restart Video is one stray press
        # away from doing something nobody asked for
        selected = self.screen.menu.items[self.screen.menu.selected_index]
        self.assertEqual(selected.text, "◀  Exit")

    def test_the_other_rows_still_do_what_they_did(self):
        labels = [i.text for i in self.screen.menu.items]
        for expected in ("Backup SD card to USB drive", "Eject USB drive",
                         "Forget all WiFi networks", "Restart Video",
                         "◀  Exit"):
            self.assertIn(expected, labels)

    # --- adjusting --------------------------------------------------------

    def test_the_mode_keys_move_through_every_choice(self):
        self.select_footswitch()
        seen = [self.item().text]
        for _ in range(len(self.e.FOOTSWITCH_ACTIONS) - 1):
            self.frame(key5_press=True)
            seen.append(self.item().text)
        self.assertEqual(seen, ["Foot Switch: Save Scene",
                                "Foot Switch: Trigger"])

    def test_it_stops_at_both_ends(self):
        self.select_footswitch()
        for _ in range(10):
            self.frame(key5_press=True)
        self.assertEqual(self.item().value, len(self.e.FOOTSWITCH_ACTIONS) - 1)
        for _ in range(10):
            self.frame(key4_press=True)
        self.assertEqual(self.item().value, 0)

    def test_adjusting_alone_does_not_write_the_config(self):
        # the same as every other settings screen, save is what commits
        self.select_footswitch()
        self.frame(key5_press=True)
        self.assertEqual(self.e.config["footswitch"], self.e.FOOTSWITCH_SAVE)
        self.assertEqual(self.written, [])

    def test_save_commits_it_to_the_config_file(self):
        self.select_footswitch()
        self.frame(key5_press=True)
        self.frame(key8_press=True)
        self.assertEqual(self.e.config["footswitch"], self.e.FOOTSWITCH_TRIGGER)
        self.assertEqual(self.written, [self.e.FOOTSWITCH_TRIGGER])

    def test_leaving_without_saving_throws_the_change_away(self):
        self.select_footswitch()
        self.frame(key5_press=True)
        self.screen.before()
        self.assertEqual(self.item().value, self.e.FOOTSWITCH_SAVE)

    def test_the_mode_keys_leave_the_action_rows_alone(self):
        # they are what moves a value, and the action rows have none
        self.screen.menu.selected_index = self.screen.menu.items.index(
            next(i for i in self.screen.menu.items if i.text == "Restart Video"))
        self.frame(key5_press=True, key4_press=True)
        self.assertFalse(getattr(self.e, "restart", False))
        self.assertEqual(self.item().value, self.e.FOOTSWITCH_SAVE)

    def test_the_footer_says_what_the_keys_do_on_each_row(self):
        self.select_footswitch()
        self.frame()
        self.assertIn("Adjust", self.screen.footer)
        self.screen.menu.selected_index = len(self.screen.menu.items) - 1
        self.frame()
        self.assertNotIn("Adjust", self.screen.footer)

    def test_the_logs_start_below_the_last_menu_row(self):
        # the pedal row pushed Exit onto the fixed y the logs used to start
        # at, so "No USB device found." landed on top of it
        rows = min(len(self.screen.menu.items), self.screen.menu.visible_items)
        last_row = 30 + self.screen.menu.off_y + (rows - 1) * 25
        row_height = 25
        self.assertGreaterEqual(self.screen.log_top(), last_row + row_height)

    def test_the_logs_still_fit_on_the_screen(self):
        # ten lines of the small font, inside the frame render_with_title draws
        self.assertLess(self.screen.log_top() + 10 * 15, 430)

    # --- the row locks while something is holding the trigger -------------

    def hold_pedal(self):
        self.e.footswitch_status = True

    def hold_b(self):
        self.e.key10_status = True

    def test_the_mode_keys_do_nothing_while_the_pedal_is_down(self):
        self.select_footswitch()
        self.hold_pedal()
        self.frame(key5_press=True)
        self.assertEqual(self.item().value, self.e.FOOTSWITCH_SAVE)

    def test_the_mode_keys_do_nothing_while_b_is_down(self):
        self.select_footswitch()
        self.hold_b()
        self.frame(key5_press=True)
        self.assertEqual(self.item().value, self.e.FOOTSWITCH_SAVE)

    def test_save_does_not_commit_while_something_is_held(self):
        # adjusted first, then a foot lands on the pedal before save
        self.select_footswitch()
        self.frame(key5_press=True)
        self.hold_pedal()
        self.frame(key8_press=True)
        self.assertEqual(self.e.config["footswitch"], self.e.FOOTSWITCH_SAVE)
        self.assertEqual(self.written, [])

    def test_it_works_again_once_everything_is_let_go(self):
        self.select_footswitch()
        self.hold_pedal()
        self.frame(key5_press=True)
        self.e.footswitch_status = False
        self.frame(key5_press=True)
        self.frame(key8_press=True)
        self.assertEqual(self.e.config["footswitch"], self.e.FOOTSWITCH_TRIGGER)

    def test_it_says_why_rather_than_looking_broken(self):
        self.select_footswitch()
        self.assertFalse(self.screen.footswitch_blocked())
        self.hold_pedal()
        self.assertTrue(self.screen.footswitch_blocked())

    def test_the_other_rows_are_not_locked_by_a_held_pedal(self):
        self.hold_pedal()
        self.screen.menu.selected_index = self.screen.menu.items.index(
            next(i for i in self.screen.menu.items if i.text == "Restart Video"))
        self.assertFalse(self.screen.footswitch_blocked())

    def test_nothing_responds_while_a_backup_is_running(self):
        self.select_footswitch()
        self.screen.state = "running"
        self.frame(key5_press=True, key8_press=True)
        self.assertEqual(self.item().value, self.e.FOOTSWITCH_SAVE)
        self.assertEqual(self.written, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
