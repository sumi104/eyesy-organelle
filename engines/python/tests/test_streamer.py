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
    pygame.transform = types.SimpleNamespace(scale=lambda *a, **k: None)
    sys.modules["pygame"] = pygame


_install_stubs()

import streamer  # noqa: E402


class FakeEyesy:
    def __init__(self, **config):
        self.xres, self.yres = 1280, 720
        self.config = {"stream_enabled": False, "stream_width": 480,
                       "stream_fps": 12}
        self.config.update(config)
        self.saves = 0

    def save_config_file(self):
        self.saves += 1


class StreamerTest(unittest.TestCase):

    def tearDown(self):
        streamer.enabled = False

    def test_frame_size_follows_the_output_aspect(self):
        e = FakeEyesy()
        self.assertEqual(streamer.frame_size(e), (480, 270))

        e.xres, e.yres = 640, 480
        self.assertEqual(streamer.frame_size(e), (480, 360))

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
