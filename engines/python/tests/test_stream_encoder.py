#!/usr/bin/env python3
"""Checks the per frame work the stream encoder does.

    python3 tests/test_stream_encoder.py

The stub pygame here is deliberately strict where the real one is: its
BufferProxy.write refuses anything that is not bytes, which is what the real
one does and what a memoryview onto the shared mapping ran into on the
instrument -- "argument 1 must be a read-only bytes-like object, not
memoryview", once a frame, forever. A permissive stub would have said the
change was fine.

The other thing worth holding still is allocation. This process grew about
eight megabytes a minute with the stream on, and with swap disabled on the
instrument that ends as a freeze that needs the plug pulled.
"""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

SURFACES = []

# one class, not a fresh one per stub: reloading the module under test
# must not leave its except clause naming a different exception
PygameError = type("error", (Exception,), {})


class FakeProxy:
    def __init__(self, surface):
        self.surface = surface

    def write(self, payload, offset=0):
        # exactly as strict as the real one
        if not isinstance(payload, bytes):
            raise TypeError("argument 1 must be a read-only bytes-like"
                            f" object, not {type(payload).__name__}")
        self.surface.written = payload


class FakeSurface:
    def __init__(self, size, flags=0, depth=0, masks=None):
        self.size = size
        self.depth = depth
        self.masks = masks
        self.written = None
        SURFACES.append(self)

    def get_view(self, kind):
        return FakeProxy(self)


def _install_stubs(scale_takes_dest=True, scale_raises=None):
    pygame = types.ModuleType("pygame")
    pygame.error = PygameError
    pygame.Surface = FakeSurface
    pygame.init = lambda: None

    def scale(surface, size, dest=None):
        if dest is not None:
            if not scale_takes_dest:
                raise TypeError("scale() takes 2 positional arguments")
            if scale_raises is not None:
                raise scale_raises("no")
            dest.scaled_from = surface
            return dest
        return FakeSurface(size)

    pygame.transform = types.SimpleNamespace(scale=scale, smoothscale=scale)
    pygame.image = types.SimpleNamespace(
        save=lambda surface, buf, name: buf.write(b"\xff\xd8jpeg"),
        frombytes=lambda data, size, fmt: FakeSurface(size),
        tobytes=lambda *a, **k: b"")
    sys.modules["pygame"] = pygame
    return pygame


_install_stubs()

import stream_encoder  # noqa: E402

MASKS = (16711680, 65280, 255, 0)


class FrameTest(unittest.TestCase):

    def setUp(self):
        SURFACES.clear()
        self.enc = stream_encoder.Encoder((640, 360), 32, MASKS)

    def test_a_frame_comes_back_as_jpeg_bytes(self):
        out = self.enc.frame(b"\x00" * 16, 2, 2)
        self.assertEqual(out, b"\xff\xd8jpeg")

    def test_only_bytes_reach_pygame(self):
        # the regression: a memoryview onto the mapping saves the copy and is
        # refused once a frame, forever
        payload = b"\x01" * 16
        self.enc.frame(payload, 2, 2)
        self.assertEqual(self.enc.src_surface.written, payload)

        with self.assertRaises(TypeError):
            self.enc.frame(memoryview(payload), 2, 2)

    def test_the_surfaces_are_made_once_not_once_a_frame(self):
        for _ in range(100):
            self.enc.frame(b"\x00" * 16, 2, 2)
        self.assertEqual(len(SURFACES), 2,
                         "one source and one destination, for a hundred frames")

    def test_a_new_source_size_makes_new_surfaces(self):
        self.enc.frame(b"\x00" * 16, 2, 2)
        made = len(SURFACES)
        self.enc.frame(b"\x00" * 36, 3, 3)
        self.assertEqual(len(SURFACES), made + 2)

    def test_the_buffer_is_reused_and_does_not_grow(self):
        buf = self.enc.buf
        for _ in range(50):
            self.enc.frame(b"\x00" * 16, 2, 2)
        self.assertIs(self.enc.buf, buf)
        self.assertEqual(len(buf.getvalue()), len(b"\xff\xd8jpeg"),
                         "truncated each time, not appended to")

    def test_it_scales_into_the_surface_it_already_has(self):
        self.enc.frame(b"\x00" * 16, 2, 2)
        self.assertIs(getattr(self.enc.out_surface, "scaled_from", None),
                      self.enc.src_surface)


class OldPygameTest(unittest.TestCase):
    """scale() only grew its destination argument in pygame 2.0."""

    def tearDown(self):
        _install_stubs()

    def rebuild(self, **kw):
        _install_stubs(**kw)
        import importlib
        importlib.reload(stream_encoder)
        SURFACES.clear()
        return stream_encoder.Encoder((640, 360), 32, MASKS)

    def test_it_falls_back_and_keeps_encoding(self):
        enc = self.rebuild(scale_takes_dest=False)
        self.assertEqual(enc.frame(b"\x00" * 16, 2, 2), b"\xff\xd8jpeg")
        self.assertFalse(enc.scale_into)

    def test_it_only_finds_out_once(self):
        # not once a frame into the caller's handler, which sleeps a second
        enc = self.rebuild(scale_takes_dest=False)
        for _ in range(20):
            enc.frame(b"\x00" * 16, 2, 2)
        # 2 on the first frame, then one allocated scale target per frame
        self.assertEqual(len(SURFACES), 2 + 20)

    def test_a_refused_destination_is_survived_too(self):
        enc = self.rebuild(scale_raises=PygameError)
        self.assertEqual(enc.frame(b"\x00" * 16, 2, 2), b"\xff\xd8jpeg")


class ScaledInEngineTest(unittest.TestCase):
    """The fallback path, where the engine sends packed RGB at target size."""

    def setUp(self):
        SURFACES.clear()
        self.enc = stream_encoder.Encoder((4, 4), 0, (0, 0, 0, 0))

    def test_it_encodes_what_it_is_given(self):
        self.assertEqual(self.enc.frame(b"\x00" * 48, 4, 4), b"\xff\xd8jpeg")

    def test_a_payload_of_the_wrong_length_is_skipped(self):
        self.assertIsNone(self.enc.frame(b"\x00" * 10, 4, 4))


class ParentDeathTest(unittest.TestCase):

    def test_the_encoder_asks_for_it_itself(self):
        self.assertTrue(hasattr(stream_encoder, "die_with_parent"))

    def test_an_orphan_gives_up_rather_than_waiting_for_a_signal(self):
        # PR_SET_PDEATHSIG only fires from the moment it is set, so a parent
        # that went while this was starting would never send anything
        real_getppid, real_exit = os.getppid, os._exit
        gone = []
        os.getppid = lambda: 1
        os._exit = lambda code: gone.append(code)
        try:
            stream_encoder.die_with_parent()
        finally:
            os.getppid, os._exit = real_getppid, real_exit
        self.assertEqual(gone, [0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
