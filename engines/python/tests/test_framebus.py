#!/usr/bin/env python3
"""Checks the shared memory frame hand off between the engine, the encoder and
the web server. Uses a temp file, so it runs anywhere, not just on Linux.

    python3 tests/test_framebus.py
"""

import os
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import framebus  # noqa: E402


class FrameBusTest(unittest.TestCase):

    def setUp(self):
        fd, self.path = tempfile.mkstemp(prefix="framebus")
        os.close(fd)
        os.unlink(self.path)
        self.capacity = 4096
        self.writer = framebus.FrameBus(self.path, self.capacity, create=True)

    def tearDown(self):
        self.writer.unlink()

    def reader(self):
        return framebus.FrameBus(self.path, self.capacity)

    def test_nothing_published_yet(self):
        self.assertIsNone(self.reader().read())

    def test_round_trip(self):
        self.writer.publish(b"\x01\x02\x03", 2, 1)
        payload, w, h, seq = self.reader().read()
        self.assertEqual(payload, b"\x01\x02\x03")
        self.assertEqual((w, h), (2, 1))
        self.assertEqual(seq, 1)

    def test_sequence_advances_and_slots_alternate(self):
        r = self.reader()
        seen = []
        for i in range(5):
            self.writer.publish(bytes([i]) * (i + 1), 8, 8)
            payload, _, _, seq = r.read()
            seen.append((payload, seq))
        self.assertEqual([s for _, s in seen], [1, 2, 3, 4, 5])
        self.assertEqual(seen[-1][0], bytes([4]) * 5)

    def test_reader_never_sees_the_slot_being_written(self):
        # publish writes the inactive slot then flips, so the payload the
        # reader is holding must stay intact across the next publish
        self.writer.publish(b"A" * 100, 4, 4)
        r = self.reader()
        first, _, _, _ = r.read()
        active_before = r._get_u32(4)
        self.writer.publish(b"B" * 100, 4, 4)
        self.assertEqual(first, b"A" * 100)
        self.assertNotEqual(active_before, r._get_u32(4))

    def test_short_frame_after_long_one(self):
        self.writer.publish(b"X" * 500, 4, 4)
        self.writer.publish(b"Y" * 3, 4, 4)
        payload, _, _, _ = self.reader().read()
        self.assertEqual(payload, b"Y" * 3)

    def test_oversized_frame_is_refused(self):
        with self.assertRaises(ValueError):
            self.writer.publish(b"0" * (self.capacity + 1), 4, 4)

    def test_takes_pixels_straight_from_a_buffer(self):
        # the engine hands over surface memory rather than serialising it
        for payload in (memoryview(b"abcd" * 8),
                        bytearray(b"wxyz" * 8),
                        memoryview(bytearray(b"1234" * 8))[4:20]):
            self.writer.publish(payload, 4, 4)
            got, _, _, _ = self.reader().read()
            self.assertEqual(got, bytes(payload))

    def test_falls_back_to_raw_for_an_old_buffer_proxy(self):
        class OldProxy:
            raw = b"legacy bytes"

        self.writer.publish(OldProxy(), 2, 2)
        got, _, _, _ = self.reader().read()
        self.assertEqual(got, b"legacy bytes")

    def test_an_oversized_buffer_is_refused_too(self):
        with self.assertRaises(ValueError):
            self.writer.publish(memoryview(bytes(self.capacity + 1)), 4, 4)

    def test_reader_rejects_a_foreign_file(self):
        path = self.path + "-junk"
        with open(path, "wb") as f:
            f.write(b"\x00" * (framebus.HEADER + self.capacity * 2))
        try:
            with self.assertRaises(ValueError):
                framebus.FrameBus(path, self.capacity)
        finally:
            os.unlink(path)

    def test_reader_missing_file(self):
        with self.assertRaises(OSError):
            framebus.FrameBus(self.path + "-nope", self.capacity)

    def test_concurrent_reads_stay_well_formed(self):
        stop = threading.Event()
        bad = []

        def read_loop():
            r = self.reader()
            while not stop.is_set():
                frame = r.read()
                if frame is None:
                    continue
                payload = frame[0]
                # every frame is a single repeated byte, a torn read would mix
                if len(set(payload)) != 1:
                    bad.append(payload)
            r.close()

        t = threading.Thread(target=read_loop)
        t.start()
        for i in range(300):
            self.writer.publish(bytes([i % 256]) * 2048, 32, 32)
        stop.set()
        t.join()
        self.assertEqual(bad, [], "reader saw a partially written frame")


if __name__ == "__main__":
    unittest.main(verbosity=2)
