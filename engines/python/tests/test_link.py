#!/usr/bin/env python3
"""Checks the Ableton Link wiring without a network or the linkd binary.

    python3 tests/test_link.py
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

import eyesy as eyesy_module   # noqa: E402
import link                    # noqa: E402
import oled                    # noqa: E402


class LinkTest(unittest.TestCase):

    def setUp(self):
        self.e = eyesy_module.Eyesy()
        self.e.config = dict(self.e.DEFAULT_CONFIG)
        link.running = False
        link.peers = 0
        link.tempo = 0.0
        oled.enabled = False

    def source(self, name):
        return self.e.TRIGGER_SOURCES.index(name)

    # --- the bit most likely to rot ------------------------------------

    def test_divisions_line_up_with_the_trigger_source_list(self):
        # link.py addresses trigger sources by index. Inserting one into the
        # middle of TRIGGER_SOURCES would silently point these somewhere else
        for index in link.DIVISIONS:
            self.assertTrue(self.e.TRIGGER_SOURCES[index].startswith("Link"),
                            f"index {index} is {self.e.TRIGGER_SOURCES[index]}")

        link_sources = [i for i, n in enumerate(self.e.TRIGGER_SOURCES)
                        if n.startswith("Link")]
        self.assertEqual(sorted(link.DIVISIONS), link_sources,
                         "every Link source needs a division and no others")

    def test_the_divisions_are_the_note_values_they_claim(self):
        beats = {"Link 16th Note": 0.25, "Link 8th Note": 0.5,
                 "Link 1/4 Note": 1.0, "Link Whole Note": 4.0}
        for name, expected in beats.items():
            self.e.config["trigger_source"] = self.source(name)
            self.assertEqual(link.division(self.e), expected, name)

    def test_only_link_sources_start_it(self):
        for name in self.e.TRIGGER_SOURCES:
            self.e.config["trigger_source"] = self.source(name)
            self.assertEqual(link.is_link_source(self.e),
                             name.startswith("Link"), name)

    def test_an_audio_source_still_has_a_sane_division(self):
        self.e.config["trigger_source"] = self.source("Audio")
        self.assertEqual(link.division(self.e), 1.0)

    # --- what the display says -----------------------------------------

    def test_describe_fits_an_oled_line(self):
        for running, peers, tempo in [(False, 0, 0.0), (True, 0, 120.0),
                                      (True, 1, 128.5), (True, 12, 174.0),
                                      (True, 99, 999.9)]:
            link.running, link.peers, link.tempo = running, peers, tempo
            self.assertLessEqual(len(link.describe()), 21, link.describe())

    def test_describe_says_whether_anyone_else_is_there(self):
        link.status(1, 0, 120.0)
        self.assertIn("alone", link.describe())
        link.status(1, 1, 120.0)
        self.assertIn("1 peer", link.describe())
        link.status(1, 3, 120.0)
        self.assertIn("3 peers", link.describe())
        link.status(0, 0, 0.0)
        self.assertEqual(link.describe(), "Link off")

    def test_the_midi_page_shows_whichever_clock_is_driving(self):
        self.e.config["trigger_source"] = self.source("MIDI Clock 1/4 Note")
        self.assertEqual(oled._clock_line(self.e), "Clock on")
        self.e.midi_clock_muted = True
        self.assertEqual(oled._clock_line(self.e), "Clock MUTED")

        self.e.midi_clock_muted = False
        self.e.config["trigger_source"] = self.source("Link 1/4 Note")
        link.status(1, 2, 120.0)
        self.assertIn("120.0", oled._clock_line(self.e))
        self.e.midi_clock_muted = True
        self.assertEqual(oled._clock_line(self.e), "Link MUTED")

    # --- lifecycle ------------------------------------------------------

    def test_a_missing_binary_is_reported_once_and_does_not_raise(self):
        link._proc = None
        link._missing_logged = False
        link.binary_path = lambda: "/nonexistent/linkd"
        self.e.config["trigger_source"] = self.source("Link 8th Note")
        link.apply(self.e)          # must not raise
        link.apply(self.e)
        self.assertTrue(link._missing_logged)

    def test_leaving_link_clears_what_was_reported(self):
        link.status(1, 4, 130.0)
        self.e.config["trigger_source"] = self.source("Audio")
        link.apply(self.e)
        self.assertFalse(link.running)
        self.assertEqual(link.peers, 0)
        self.assertEqual(link.describe(), "Link off")


if __name__ == "__main__":
    unittest.main(verbosity=2)
