#!/usr/bin/env python3
"""The MIDI page's two new rows: the clock and the last program change.

    python3 tests/test_midi_page.py

The page has five rows and the nine CC numbers used to take two of them, with
nothing to say which number was which -- five three digit numbers and their
gaps come to nineteen of the twenty one characters, so there was never room
for a label. These two rows replaced them.
"""

import os
import random
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

    def test_it_says_nothing_until_it_has_a_whole_window(self):
        self.now = feed(120.0, midi.CLOCK_WINDOW_TICKS)
        self.assertEqual(midi.clock_bpm(), 0.0)

    def test_a_steady_clock_reads_its_tempo(self):
        for bpm in (60.0, 120.0, 174.0):
            midi.clock_reset()
            self.now = feed(bpm, midi.CLOCK_WINDOW_TICKS + 1)
            self.assertAlmostEqual(midi.clock_bpm(), bpm, places=6)

    def test_it_keeps_reading_it_over_many_beats(self):
        self.now = feed(128.0, midi.CLOCK_WINDOW_TICKS * 8)
        self.assertAlmostEqual(midi.clock_bpm(), 128.0, places=6)

    def test_jitter_is_smoothed_rather_than_shown(self):
        # one late tick must not throw the reading around
        self.now = feed(120.0, midi.CLOCK_WINDOW_TICKS * 4)
        steady = midi.clock_bpm()
        midi._note_clock_tick(self.now + 0.03)      # a tick well out of place
        self.assertLess(abs(midi.clock_bpm() - steady), 8.0,
                        "one late tick should nudge it, not move it")

    def test_a_stopped_clock_goes_quiet(self):
        # nothing here reads a stop message, so silence is the only sign
        self.now = feed(120.0, midi.CLOCK_WINDOW_TICKS + 1)
        self.assertGreater(midi.clock_bpm(), 0)
        self.now += midi.CLOCK_SILENCE + 0.1
        self.assertEqual(midi.clock_bpm(), 0.0)

    def test_a_gap_is_not_read_as_a_tempo(self):
        # a pause mid stream would otherwise measure as something very slow
        self.now = feed(120.0, midi.CLOCK_WINDOW_TICKS * 2)
        steady = midi.clock_bpm()
        midi._note_clock_tick(self.now + 30.0)
        self.assertAlmostEqual(midi.clock_bpm(), steady, places=6)

    def test_muting_the_clock_does_not_stop_measuring_it(self):
        # G# stops the visuals following it, it does not stop it arriving,
        # and the page says what is out there either way
        e = FakeEyesy(source=CLOCK_QUARTER, muted=True)
        interval = 60.0 / (120.0 * midi.CLOCK_TICKS_PER_BEAT)
        for i in range(midi.CLOCK_WINDOW_TICKS + 1):
            self.now = i * interval
            midi._handle_clock(e, Msg(type="clock"))
        self.assertAlmostEqual(midi.clock_bpm(), 120.0, places=6)

    def test_a_muted_clock_still_fires_nothing(self):
        e = FakeEyesy(source=CLOCK_QUARTER, muted=True)
        e.trig = False
        for _ in range(midi.CLOCK_WINDOW_TICKS * 2):
            midi._handle_clock(e, Msg(type="clock"))
        self.assertFalse(e.trig)


class BatchedArrivalTest(unittest.TestCase):
    """The tempo as the engine actually sees the ticks.

    recv() drains the port once per video frame, so a tick is stamped with
    the moment the engine got to it rather than the moment it arrived, and
    every tick in a batch shares one timestamp. Reported from the instrument:
    Live sending a flat 161 and the page wandering between 141 and 161,
    because a measurement one frame wide either way moves the answer by ten
    BPM at that tempo.
    """

    def setUp(self):
        midi.clock_reset()
        self.now = 0.0
        self.due = 0.0
        self.real = midi.time.monotonic
        midi.time.monotonic = lambda: self.now

    def tearDown(self):
        midi.time.monotonic = self.real
        midi.clock_reset()

    def restart(self):
        midi.clock_reset()
        self.now = self.due = 0.0

    def batched(self, bpm, seconds, frame=1 / 30.0):
        # carries on from where the last call left off, so a test can run one
        # tempo and then another without the clock jumping backwards
        interval = 60.0 / (bpm * midi.CLOCK_TICKS_PER_BEAT)
        end = self.now + seconds
        while self.now < end:
            self.now += frame
            while self.due <= self.now:
                midi._note_clock_tick(self.now)  # the frame's time, not the tick's
                self.due += interval

    def test_a_flat_tempo_reads_flat(self):
        self.batched(161.0, 20.0)
        self.assertAlmostEqual(midi.clock_bpm(), 161.0, delta=1.0)

    def test_it_holds_still_rather_than_wandering(self):
        self.batched(161.0, 20.0)
        settled = midi.clock_bpm()
        seen = set()
        for _ in range(40):
            self.batched(161.0, 0.5)
            seen.add(midi.clock_bpm())
        self.assertLessEqual(len(seen), 2,
                             f"settled at {settled}, then showed {sorted(seen)}")

    def test_it_works_at_other_tempos_too(self):
        for bpm in (60.0, 90.0, 128.0, 174.0):
            self.restart()
            self.batched(bpm, 20.0)
            self.assertAlmostEqual(midi.clock_bpm(), bpm, delta=1.0, msg=f"{bpm}")

    def jittered(self, bpm, seconds, jitter=0.2, seed=1, frame=1 / 30.0):
        """Batched arrival, plus the send and the render loop both wobbling.

        A DAW down a USB cable does not place its ticks on a grid, and the
        render loop is not a metronome either -- a heavy mode takes longer.
        """
        rnd = random.Random(seed)
        interval = 60.0 / (bpm * midi.CLOCK_TICKS_PER_BEAT)
        end = self.now + seconds
        while self.now < end:
            self.now += frame * rnd.uniform(0.8, 1.4)
            while self.due <= self.now:
                midi._note_clock_tick(self.now)
                self.due += interval * rnd.uniform(1 - jitter, 1 + jitter)

    def test_the_noise_is_averaged_away_not_locked_in(self):
        # The smoothing is heavy enough that the first measurement would
        # otherwise stand for a minute, and one measurement is a span between
        # two timestamps a frame apart -- the very thing being averaged away.
        # So it opens as a running mean and eases into the exponential one.
        for seed in (1, 2, 3, 4, 5):
            self.restart()
            self.jittered(161.0, 30.0, seed=seed)
            self.assertAlmostEqual(midi.clock_bpm(), 161.0, delta=1.0,
                                   msg=f"seed {seed}")

    def test_a_real_change_is_followed(self):
        self.batched(120.0, 15.0)
        self.assertAlmostEqual(midi.clock_bpm(), 120.0, delta=1.0)
        self.batched(140.0, 15.0)
        self.assertAlmostEqual(midi.clock_bpm(), 140.0, delta=1.0)


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


class ActivityLampTest(unittest.TestCase):
    """The dot on the MIDI page's channel row.

    Reported from the instrument: it never lit while Live was sending clock
    and program changes. It was reading eyesy.midi_notes -- a note being held
    down, on the configured channel, and not while notes were muted. This
    page is where you go to find out whether MIDI is arriving at all, so the
    lamp is anything arriving, before the channel is looked at.
    """

    def setUp(self):
        midi.last_message_at = 0.0
        midi.clock_reset()
        self.now = 100.0
        self.real = midi.time.monotonic
        midi.time.monotonic = lambda: self.now

    def tearDown(self):
        midi.time.monotonic = self.real
        midi.last_message_at = 0.0

    def test_nothing_arriving_is_dark(self):
        self.assertFalse(midi.receiving())

    def test_it_lights_on_anything(self):
        midi.last_message_at = self.now
        self.assertTrue(midi.receiving())

    def test_it_goes_out_when_the_cable_does(self):
        midi.last_message_at = self.now
        self.now += midi.MESSAGE_HOLD + 0.01
        self.assertFalse(midi.receiving())

    def test_one_message_is_held_long_enough_to_see(self):
        # the display refreshes twenty times a second, so a single program
        # change has to outlast at least one of those
        self.assertGreater(midi.MESSAGE_HOLD, 1 / 20.0)

    def test_a_clock_keeps_it_lit(self):
        for _ in range(5):
            midi.last_message_at = self.now
            self.now += 0.02          # 24 ticks a beat at any usable tempo
            self.assertTrue(midi.receiving())

    # --- through recv(), which is where it is actually marked -------------

    def port(self, *messages):
        return types.SimpleNamespace(iter_pending=lambda: iter(messages))

    def test_every_kind_of_message_marks_it(self):
        for msg in (Msg(type="clock"),
                    Msg(type="program_change", channel=0, program=4),
                    Msg(type="control_change", channel=0, control=74, value=1),
                    Msg(type="note_on", channel=0, note=60, velocity=100)):
            midi.last_message_at = 0.0
            midi.recv(FakeEyesy(), self.port(msg))
            self.assertTrue(midi.receiving(), msg.type)

    def test_a_message_for_another_channel_marks_it_too(self):
        # the lamp answers "is it reaching this", and a wrong channel is one
        # of the two things it has to tell apart from a wrong cable. The
        # channel it is set to is on the same row
        midi.recv(FakeEyesy(), self.port(
            Msg(type="control_change", channel=9, control=74, value=1)))
        self.assertTrue(midi.receiving())

    def test_a_quiet_port_leaves_it_alone(self):
        midi.recv(FakeEyesy(), self.port())
        self.assertFalse(midi.receiving())


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
        feed(140.0, midi.CLOCK_WINDOW_TICKS + 1)
        row = oled.clock_text(FakeEyesy(source=CLOCK_QUARTER))
        self.assertIn("140", row)

    def test_a_muted_midi_clock_keeps_its_tempo_too(self):
        feed(140.0, midi.CLOCK_WINDOW_TICKS + 1)
        row = oled.clock_text(FakeEyesy(source=CLOCK_QUARTER, muted=True))
        self.assertIn("140", row)
        self.assertIn("muted", row)

    def test_a_midi_clock_with_nothing_arriving_says_so(self):
        row = oled.clock_text(FakeEyesy(source=CLOCK_QUARTER))
        self.assertIn("--", row)

    def test_link_and_the_clock_are_told_apart_by_name(self):
        link.running, link.tempo = True, 120.0
        feed(120.0, midi.CLOCK_WINDOW_TICKS + 1)
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
                    feed(199.9, midi.CLOCK_WINDOW_TICKS + 1)
                    row = oled.clock_text(FakeEyesy(source=source, muted=muted))
                    self.assertLessEqual(len(row), OLED_LINE, row)


class ProgramRowTest(unittest.TestCase):

    def setUp(self):
        midi.last_program = 0

    def tearDown(self):
        midi.last_program = 0

    def test_it_says_it_is_waiting_rather_than_sitting_empty(self):
        # a blank row on the page you just set a mapping up for reads as the
        # feature being broken, not as nothing having been sent yet
        row = oled.program_text(FakeEyesy())
        self.assertIn("PGM", row)
        self.assertIn("--", row)

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
