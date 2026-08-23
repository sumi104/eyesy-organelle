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

    def test_the_session_is_still_tracked_with_nowhere_to_show_it(self):
        # describe() went with the clock row. peers and tempo are still kept
        # up to date because the trigger reads them, and because a readout
        # would need them again if one is ever wanted.
        link.status(1, 3, 128.5)
        self.assertTrue(link.running)
        self.assertEqual(link.peers, 3)
        self.assertEqual(link.tempo, 128.5)
        link.status(0, 0, 0.0)
        self.assertFalse(link.running)

    # The MIDI page used to carry a clock row saying which clock was driving
    # and, for Link, its tempo and peer count. That row is gone. What is left
    # on the display is the trigger source, on the status page, and the mute
    # letter in the top bar - so a Link session is still visible as the thing
    # selected, just not as a tempo.
    def test_the_display_still_says_a_link_source_is_selected(self):
        for name in ("Link 16th Note", "Link 8th Note",
                     "Link 1/4 Note", "Link Whole Note"):
            self.e.config["trigger_source"] = self.source(name)
            short = oled.trig_text(self.e)
            self.assertTrue(short.startswith("Link"), short)
            self.assertLessEqual(len(short), 10, f"{short} will not fit")

    def test_every_trigger_source_has_a_short_name_that_fits(self):
        # ten characters is what the status page leaves after "Trig Src  "
        self.assertEqual(len(oled.TRIG_SHORT), len(self.e.TRIGGER_SOURCES))
        for i in range(len(self.e.TRIGGER_SOURCES)):
            self.e.config["trigger_source"] = i
            self.assertLessEqual(len(oled.trig_text(self.e)), 10)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
