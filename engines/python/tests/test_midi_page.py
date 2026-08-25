#!/usr/bin/env python3
"""The MIDI page's two new rows: the clock and the last program change.

    python3 tests/test_midi_page.py

The page has five rows and the nine CC numbers used to take two of them, with
nothing to say which number was which -- five three digit numbers and their
gaps come to nineteen of the twenty one characters, so there was never room
for a label. These two rows replaced them.
"""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.chdir(os.path.dirname(HERE))


def _install_stubs():
    mido = types.ModuleType("mido")
    mido.open_input = lambda *a, **k: None
    mido.get_input_names = lambda: []
    sys.modules["mido"] = mido

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

import link                          # noqa: E402
import midi                          # noqa: E402
import oled                          # noqa: E402

# trigger_source values, as eyesy.TRIGGER_SOURCES indexes them
AUDIO, CLOCK_QUARTER, LINK_QUARTER = 0, 5, 9

OLED_LINE = 21


class FakeEyesy:
    def __init__(self, source=AUDIO, muted=False, pc_map=None):
        self.midi_clock_muted = muted
        self.midi_notes_muted = False
        self.menu_mode = False
        self.config = {"trigger_source": source, "midi_channel": 1,
                       "pc_map": pc_map or {}}
        self.recalled = []

    def recall_scene_by_name(self, name):
        self.recalled.append(name)


class Msg:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def feed(bpm, count, start=0.0):
    """count clock ticks arriving at a steady tempo."""
    interval = 60.0 / (bpm * midi.CLOCK_TICKS_PER_BEAT)
    for i in range(count):
        midi._note_clock_tick(start + (i * interval))
    return start + ((count - 1) * interval)


class ClockTempoTest(unittest.TestCase):

    def setUp(self):
        midi.clock_reset()
        self.now = 0.0
        self.real = midi.time.monotonic
        midi.time.monotonic = lambda: self.now

    def tearDown(self):
        midi.time.monotonic = self.real
        midi.clock_reset()

    def test_nothing_yet_is_no_tempo(self):
        self.assertEqual(midi.clock_bpm(), 0.0)

    def test_it_takes_a_whole_beat_before_it_says_anything(self):
        # 24 ticks to the quarter note, and the span of one is what is
        # measured -- a single tick is mostly jitter
        self.now = feed(120.0, midi.CLOCK_TICKS_PER_BEAT)
        self.assertEqual(midi.clock_bpm(), 0.0)

    def test_a_steady_clock_reads_its_tempo(self):
        for bpm in (60.0, 120.0, 174.0):
            midi.clock_reset()
            self.now = feed(bpm, midi.CLOCK_TICKS_PER_BEAT + 1)
            self.assertAlmostEqual(midi.clock_bpm(), bpm, places=6)

    def test_it_keeps_reading_it_over_many_beats(self):
        self.now = feed(128.0, midi.CLOCK_TICKS_PER_BEAT * 8)
        self.assertAlmostEqual(midi.clock_bpm(), 128.0, places=6)

    def test_jitter_is_smoothed_rather_than_shown(self):
        # one late tick must not throw the reading around
        self.now = feed(120.0, midi.CLOCK_TICKS_PER_BEAT * 4)
        steady = midi.clock_bpm()
        midi._note_clock_tick(self.now + 0.03)      # a tick well out of place
        self.assertLess(abs(midi.clock_bpm() - steady), 8.0,
                        "one late tick should nudge it, not move it")

    def test_a_stopped_clock_goes_quiet(self):
        # nothing here reads a stop message, so silence is the only sign
        self.now = feed(120.0, midi.CLOCK_TICKS_PER_BEAT + 1)
        self.assertGreater(midi.clock_bpm(), 0)
        self.now += midi.CLOCK_SILENCE + 0.1
        self.assertEqual(midi.clock_bpm(), 0.0)

    def test_a_gap_is_not_read_as_a_tempo(self):
        # a pause mid stream would otherwise measure as something very slow
        self.now = feed(120.0, midi.CLOCK_TICKS_PER_BEAT * 2)
        steady = midi.clock_bpm()
        midi._note_clock_tick(self.now + 30.0)
        self.assertAlmostEqual(midi.clock_bpm(), steady, places=6)

    def test_muting_the_clock_does_not_stop_measuring_it(self):
        # G# stops the visuals following it, it does not stop it arriving,
        # and the page says what is out there either way
        e = FakeEyesy(source=CLOCK_QUARTER, muted=True)
        interval = 60.0 / (120.0 * midi.CLOCK_TICKS_PER_BEAT)
        for i in range(midi.CLOCK_TICKS_PER_BEAT + 1):
            self.now = i * interval
            midi._handle_clock(e, Msg(type="clock"))
        self.assertAlmostEqual(midi.clock_bpm(), 120.0, places=6)

    def test_a_muted_clock_still_fires_nothing(self):
        e = FakeEyesy(source=CLOCK_QUARTER, muted=True)
        e.trig = False
        for _ in range(midi.CLOCK_TICKS_PER_BEAT * 2):
            midi._handle_clock(e, Msg(type="clock"))
        self.assertFalse(e.trig)


class ProgramChangeTest(unittest.TestCase):

    def setUp(self):
        midi.last_program = 0

    def tearDown(self):
        midi.last_program = 0

    def send(self, e, program):
        midi._handle_program_change(e, Msg(channel=0, program=program))

    def test_it_is_remembered_the_way_the_settings_screen_counts(self):
        # the wire carries 0 to 127, that screen lists pgm 1 to 128, and a
        # sender that disagrees about which end to count from is the reason
        # this row exists
        e = FakeEyesy(pc_map={"pgm_5": "scene-0003"})
        self.send(e, 4)
        self.assertEqual(midi.last_program, 5)
        self.assertEqual(e.recalled, ["scene-0003"])

    def test_an_unmapped_number_is_remembered_too(self):
        # "it arrived and nothing is assigned" is the answer you want when a
        # program change did nothing at all
        e = FakeEyesy(pc_map={})
        self.send(e, 41)
        self.assertEqual(midi.last_program, 42)
        self.assertEqual(e.recalled, [])

    def test_another_channel_is_not_remembered(self):
        e = FakeEyesy(pc_map={})
        midi._handle_program_change(e, Msg(channel=7, program=3))
        self.assertEqual(midi.last_program, 0)

    def test_the_newest_one_wins(self):
        e = FakeEyesy(pc_map={})
        for p in (0, 9, 99):
            self.send(e, p)
        self.assertEqual(midi.last_program, 100)


class ClockRowTest(unittest.TestCase):

    def setUp(self):
        midi.clock_reset()
        link.running, link.peers, link.tempo = False, 0, 0.0

    def tearDown(self):
        midi.clock_reset()
        link.running, link.peers, link.tempo = False, 0, 0.0

    def test_it_is_empty_when_no_clock_drives_anything(self):
        self.assertEqual(oled.clock_text(FakeEyesy(source=AUDIO)), "")

    def test_link_shows_tempo_and_peers(self):
        link.running, link.peers, link.tempo = True, 3, 128.5
        row = oled.clock_text(FakeEyesy(source=LINK_QUARTER))
        self.assertIn("128.5", row)
        self.assertIn("3p", row)

    def test_link_not_answering_says_so(self):
        # linkd is GPL and not in this tree, so it may simply not be built
        row = oled.clock_text(FakeEyesy(source=LINK_QUARTER))
        self.assertIn("off", row)

    def test_a_muted_link_keeps_its_tempo_on_screen(self):
        link.running, link.peers, link.tempo = True, 2, 120.0
        row = oled.clock_text(FakeEyesy(source=LINK_QUARTER, muted=True))
        self.assertIn("120.0", row)
        self.assertIn("muted", row)

    def test_the_midi_clock_shows_its_measured_tempo(self):
        feed(140.0, midi.CLOCK_TICKS_PER_BEAT + 1)
        row = oled.clock_text(FakeEyesy(source=CLOCK_QUARTER))
        self.assertIn("140.0", row)

    def test_a_muted_midi_clock_keeps_its_tempo_too(self):
        feed(140.0, midi.CLOCK_TICKS_PER_BEAT + 1)
        row = oled.clock_text(FakeEyesy(source=CLOCK_QUARTER, muted=True))
        self.assertIn("140.0", row)
        self.assertIn("muted", row)

    def test_a_midi_clock_with_nothing_arriving_says_so(self):
        row = oled.clock_text(FakeEyesy(source=CLOCK_QUARTER))
        self.assertIn("--", row)

    def test_link_and_the_clock_are_told_apart_by_name(self):
        link.running, link.tempo = True, 120.0
        feed(120.0, midi.CLOCK_TICKS_PER_BEAT + 1)
        self.assertTrue(oled.clock_text(
            FakeEyesy(source=LINK_QUARTER)).startswith("Link"))
        self.assertTrue(oled.clock_text(
            FakeEyesy(source=CLOCK_QUARTER)).startswith("Clock"))

    def test_every_form_of_it_fits_a_row(self):
        for running, peers, tempo in ((True, 12, 199.9), (True, 250, 999.9),
                                      (False, 0, 0.0)):
            link.running, link.peers, link.tempo = running, peers, tempo
            for muted in (False, True):
                for source in (LINK_QUARTER, CLOCK_QUARTER, AUDIO):
                    feed(199.9, midi.CLOCK_TICKS_PER_BEAT + 1)
                    row = oled.clock_text(FakeEyesy(source=source, muted=muted))
                    self.assertLessEqual(len(row), OLED_LINE, row)


class ProgramRowTest(unittest.TestCase):

    def setUp(self):
        midi.last_program = 0

    def tearDown(self):
        midi.last_program = 0

    def test_it_is_empty_until_one_arrives(self):
        self.assertEqual(oled.program_text(FakeEyesy()), "")

    def test_a_mapped_one_names_the_scene(self):
        midi.last_program = 5
        row = oled.program_text(FakeEyesy(pc_map={"pgm_5": "scene-0003"}))
        self.assertIn("5", row)
        self.assertIn("scene-0003", row)

    def test_an_unmapped_one_says_that_instead_of_going_blank(self):
        midi.last_program = 7
        row = oled.program_text(FakeEyesy(pc_map={"pgm_5": "scene-0003"}))
        self.assertIn("7", row)
        self.assertIn("not mapped", row)

    def test_a_long_scene_name_is_cut_rather_than_pushed_off(self):
        midi.last_program = 128
        row = oled.program_text(
            FakeEyesy(pc_map={"pgm_128": "a scene with a very long name"}))
        self.assertLessEqual(len(row), OLED_LINE)
        self.assertTrue(row.startswith("PGM 128"))

    def test_every_number_fits_a_row(self):
        for n in (1, 9, 10, 99, 100, 128):
            midi.last_program = n
            for pc_map in ({}, {f"pgm_{n}": "scene-0002"}):
                row = oled.program_text(FakeEyesy(pc_map=pc_map))
                self.assertLessEqual(len(row), OLED_LINE, row)


if __name__ == "__main__":
    unittest.main(verbosity=2)
