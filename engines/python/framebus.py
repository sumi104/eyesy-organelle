"""A one frame wide pipe between processes, backed by a file in /dev/shm.

Three programs need to hand frames around: the video engine produces them, the
encoder turns them into JPEG, and the web server serves them. They are separate
services, so this deliberately avoids multiprocessing.shared_memory, whose
resource tracker unlinks segments when an unrelated reader exits.

Two slots and an active index give the reader a stable buffer to copy out of
while the writer fills the other one.

Layout:
    0   uint32  magic
    4   uint32  active slot, 0 or 1
    8   uint32  sequence, bumped on every publish
    12  uint32  width
    16  uint32  height
    20  uint32  slot 0 payload length
    24  uint32  slot 1 payload length
    32          slot 0 payload
    32+cap      slot 1 payload
"""

import mmap
import os
import struct

HEADER = 32
MAGIC = 0x45590001

RAW_PATH = "/dev/shm/eyesy_frame_raw"
JPEG_PATH = "/dev/shm/eyesy_frame_jpeg"


class FrameBus:

    def __init__(self, path, capacity, create=False):
        self.path = path
        self.capacity = capacity
        self.size = HEADER + (capacity * 2)
        self._slot = 0

        if create:
            fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o666)
            os.ftruncate(fd, self.size)
            self.map = mmap.mmap(fd, self.size)
            os.close(fd)
            self._put_u32(0, MAGIC)
            self._put_u32(4, 0)
            self._put_u32(8, 0)
        else:
            fd = os.open(path, os.O_RDONLY)
            try:
                self.map = mmap.mmap(fd, self.size, prot=mmap.PROT_READ)
            finally:
                os.close(fd)
            if self._get_u32(0) != MAGIC:
                raise ValueError(f"{path} is not a frame bus")

    def _get_u32(self, offset):
        return struct.unpack_from("<I", self.map, offset)[0]

    def _put_u32(self, offset, value):
        struct.pack_into("<I", self.map, offset, value)

    def publish(self, payload, width, height):
        """Write into the slot the reader is not looking at, then flip.

        Takes anything supporting the buffer protocol, so a caller with pixels
        already in memory can hand them straight over instead of serialising
        them into a bytes object first.
        """
        try:
            payload = memoryview(payload)
            length = payload.nbytes
        except TypeError:
            # pygame's BufferProxy on older builds, .raw costs one more copy
            payload = payload.raw
            length = len(payload)

        if length > self.capacity:
            raise ValueError(f"frame of {length} exceeds {self.capacity}")

        slot = 1 - self._get_u32(4)
        start = HEADER + (slot * self.capacity)
        self.map[start:start + length] = payload
        self._put_u32(20 + (slot * 4), length)
        self._put_u32(12, width)
        self._put_u32(16, height)
        self._put_u32(4, slot)
        self._put_u32(8, self._get_u32(8) + 1)

    def sequence(self):
        return self._get_u32(8)

    def read(self):
        """Returns (payload, width, height, sequence) or None if nothing yet."""
        seq = self._get_u32(8)
        if seq == 0:
            return None
        slot = self._get_u32(4)
        length = self._get_u32(20 + (slot * 4))
        if length == 0 or length > self.capacity:
            return None
        start = HEADER + (slot * self.capacity)
        return (bytes(self.map[start:start + length]),
                self._get_u32(12), self._get_u32(16), seq)

    def close(self):
        try:
            self.map.close()
        except Exception:
            pass

    def unlink(self):
        self.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass
