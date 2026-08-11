#!/usr/bin/env python3
"""Checks the live stream settings maths and the on/off toggle.

    python3 tests/test_streamer.py

Stubs pygame, so it runs on a laptop. Does not start an encoder.
"""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))


def _install_stubs():
    pygame = types.ModuleType("pygame")
    pygame.Surface = lambda *a, **k: object()
    pygame.image = types.SimpleNamespace(tobytes=lambda *a, **k: b"",
                                         frombytes=lambda *a, **k: None)
    pygame.transform = types.SimpleNamespace(scale=lambda *a, **k: None,
                                             smoothscale=lambda *a, **k: None)

    class _Font:
        def __init__(self, *a, **k):
            pass

    pygame.font = types.SimpleNamespace(Font=_Font)
    sys.modules["pygame"] = pygame


_install_stubs()

import screen_video_settings as svs  # noqa: E402
import streamer  # noqa: E402


class FakeEyesy:
    RESOLUTIONS = [{"name": "1280 x 720", "res": (1280, 720)}]
    COMPVIDS = ["NTSC", "PAL"]

    def __init__(self, **config):
        self.xres, self.yres = 1280, 720
        self.config = {"stream_enabled": False, "stream_width": 640,
                       "stream_fps": 15, "stream_smooth": False,
                       "video_resolution": 0}
        self.config.update(config)
        self.saves = 0
        self.ip = ""
        self.screens = []
        self.key4_press = self.key5_press = False
        self.key4_status = self.key5_status = False
        self.key6_press = self.key7_press = self.key8_press = False
        self.key6_status = self.key7_status = False

    def save_config_file(self):
        self.saves += 1

    def switch_menu_screen(self, name):
        self.screens.append(name)


class StreamerTest(unittest.TestCase):

    def tearDown(self):
        streamer.enabled = False

    def test_frame_size_follows_the_output_aspect(self):
        e = FakeEyesy(stream_width=480)
        self.assertEqual(streamer.frame_size(e), (480, 270))

        e.xres, e.yres = 640, 480
        self.assertEqual(streamer.frame_size(e), (480, 360))

    def test_the_default_width_halves_the_default_output(self):
        # an exact divisor is what keeps nearest neighbour scaling clean
        e = FakeEyesy()
        self.assertEqual(streamer.frame_size(e), (640, 360))

    def test_frame_height_is_always_even(self):
        # jpeg chroma subsampling wants even dimensions
        for xres, yres in [(1280, 720), (720, 480), (800, 600), (1920, 1080)]:
            e = FakeEyesy()
            e.xres, e.yres = xres, yres
            for width in streamer.WIDTHS:
                e.config["stream_width"] = width
                _, height = streamer.frame_size(e)
                self.assertEqual(height % 2, 0, f"{width} of {xres}x{yres}")

    def test_a_bad_width_falls_back(self):
        e = FakeEyesy(stream_width=9999)
        self.assertEqual(streamer.frame_size(e)[0], 480)

    def test_describe_fits_an_oled_line(self):
        for xres, yres in [(1280, 720), (1920, 1080), (720, 480)]:
            e = FakeEyesy()
            e.xres, e.yres = xres, yres
            for width in streamer.WIDTHS:
                e.config["stream_width"] = width
                line = streamer.describe(e)
                self.assertLessEqual(len(line), 21, line)

    def test_toggle_flips_and_saves(self):
        e = FakeEyesy()
        # init fails without /dev/shm, which is fine, the flag is what matters
        self.assertTrue(streamer.toggle(e))
        self.assertTrue(e.config["stream_enabled"])
        self.assertEqual(e.saves, 1)

        self.assertFalse(streamer.toggle(e))
        self.assertFalse(e.config["stream_enabled"])
        self.assertEqual(e.saves, 2)

    def test_publish_is_inert_while_off(self):
        streamer.enabled = False
        streamer.publish(object())   # must not raise or touch pygame


class StreamMenuTest(unittest.TestCase):
    """The menu holds list indices while the config holds real values, which
    is exactly the sort of mapping that quietly gets off by one."""

    def setUp(self):
        self.e = FakeEyesy()
        self.screen = svs.ScreenVideoSettings(self.e)
        streamer.enabled = False

    def tearDown(self):
        streamer.enabled = False

    def item(self, name):
        return self.screen.stream_item(name)

    def test_values_round_trip_through_the_menu(self):
        self.e.config.update({"stream_enabled": True, "stream_width": 960,
                              "stream_fps": 30, "stream_smooth": True})
        self.screen.select_stream()

        self.assertEqual(self.item("stream_width").value,
                         streamer.WIDTHS.index(960))
        self.assertEqual(self.item("stream_fps").value,
                         svs.STREAM_RATES.index(30))
        self.assertEqual(self.item("stream_enabled").value, 1)

        self.screen.save_stream()
        self.assertEqual(self.e.config["stream_width"], 960)
        self.assertEqual(self.e.config["stream_fps"], 30)
        self.assertIs(self.e.config["stream_enabled"], True)
        self.assertIs(self.e.config["stream_smooth"], True)

    def test_labels_show_the_real_value_not_the_index(self):
        self.e.config.update({"stream_width": 960, "stream_fps": 30})
        self.screen.select_stream()
        self.assertIn("960", self.item("stream_width").text)
        self.assertIn("30", self.item("stream_fps").text)

    def test_adjusting_clamps_at_both_ends(self):
        self.screen.select_stream()
        width = self.item("stream_width")

        for _ in range(20):
            self.screen.menu_inc_value(width)
        self.assertEqual(width.value, len(streamer.WIDTHS) - 1)
        self.screen.save_stream()
        self.assertEqual(self.e.config["stream_width"], streamer.WIDTHS[-1])

        self.screen.select_stream()
        for _ in range(20):
            self.screen.menu_dec_value(width)
        self.assertEqual(width.value, 0)
        self.screen.save_stream()
        self.assertEqual(self.e.config["stream_width"], streamer.WIDTHS[0])

    def test_a_config_value_outside_the_list_does_not_crash(self):
        self.e.config["stream_width"] = 1234
        self.e.config["stream_fps"] = 7
        self.screen.select_stream()
        self.assertEqual(self.item("stream_width").value, 0)
        self.assertEqual(self.item("stream_fps").value, 0)

    def test_nothing_is_written_until_save(self):
        self.screen.select_stream()
        self.screen.menu_inc_value(self.item("stream_width"))
        self.screen.menu_inc_value(self.item("stream_fps"))
        self.assertEqual(self.e.config["stream_width"], 640)
        self.assertEqual(self.e.config["stream_fps"], 15)
        self.assertEqual(self.e.saves, 0, "adjusting must not hit the disk")

        self.screen.save_stream()
        self.assertEqual(self.e.saves, 1)
        self.assertEqual(self.e.screens[-1], "home")

    def test_exiting_discards_the_changes(self):
        self.screen.select_stream()
        self.screen.menu_inc_value(self.item("stream_width"))
        self.screen.goto_home()
        self.assertEqual(self.e.config["stream_width"], 640)
        self.assertEqual(self.e.saves, 0)

    def test_footer_switches_to_the_adjust_legend(self):
        self.screen.before()
        self.assertEqual(self.screen.footer, svs.FOOTER_PLAIN)
        self.screen.select_stream()
        self.assertEqual(self.screen.footer, svs.FOOTER_ADJUST)


if __name__ == "__main__":
    unittest.main(verbosity=2)
