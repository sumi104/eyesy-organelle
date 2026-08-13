"""Turns the render loop's surface into motion JPEG for the browser.

The instrument splits this across three processes through /dev/shm, because a
CM3 cannot afford to scale and JPEG encode inside a 33ms frame budget. macOS
has no /dev/shm, so the framebus and the encoder process collapse into this
file — but the reason for the split survives the move, because pygame's JPEG
encoder is not fast:

    scale 1280x720 -> 640x360      2.5ms
    smoothscale     "              17.6ms
    jpeg 640x360                   17ms
    jpeg 1280x720                  60ms
    blit into a staging surface     1.8ms

(measured on a 2020 Intel MacBook Air; Pillow was tried and came out slower.)

So the render loop pays for the blit and nothing else, and a worker thread
does the scale and the encode. Without that, streaming at 640 costs two thirds
of the frame budget and the visuals themselves stutter — which is exactly the
thing a simulator must not do, since stutter is what you would be trying to
diagnose.

The staging surface is written under the lock and copied out under the lock,
so a viewer never sees half of one frame and half of the next.
"""

import io
import threading
import time

import pygame

WIDTHS = [320, 480, 640, 960, 1280]


class FrameStream:

    def __init__(self, width=640, fps=20, smooth=True):
        self.width = width
        self.fps = max(1, min(30, int(fps)))
        self.smooth = smooth

        # render loop -> encoder
        self._src_cond = threading.Condition()
        self._staging = None
        self._staging_seq = 0
        self._encoded_seq = 0

        # encoder -> viewers
        self._out_cond = threading.Condition()
        self._jpeg = None
        self._seq = 0

        self._interval = 1.0 / self.fps
        self._next_frame = 0.0
        self._worker = None

        # what each half actually costs, shown in the UI so a mode that draws
        # slowly can be told apart from a stream that is set too large
        self.publish_ms = 0.0
        self.encode_ms = 0.0

    def configure(self, width=None, fps=None, smooth=None):
        if width is not None:
            self.width = int(width)
        if fps is not None:
            self.fps = max(1, min(30, int(fps)))
            self._interval = 1.0 / self.fps
        if smooth is not None:
            self.smooth = bool(smooth)

    def _target_size(self, size):
        w, h = size
        width = min(self.width, w)
        height = int(width * h / w) & ~1
        return width, height

    # ---- render loop side -------------------------------------------------

    def publish(self, surface):
        """Called every frame from the render loop. Rate limited, and cheap."""
        now = time.monotonic()
        if now < self._next_frame:
            return
        # anchored to now, so one slow frame does not leave a backlog to
        # sprint through afterwards
        self._next_frame = now + self._interval

        if self._worker is None:
            self._worker = threading.Thread(target=self._encode_loop,
                                            daemon=True)
            self._worker.start()

        try:
            with self._src_cond:
                if self._staging is None or \
                        self._staging.get_size() != surface.get_size():
                    self._staging = pygame.Surface(surface.get_size(), 0,
                                                   surface)
                self._staging.blit(surface, (0, 0))
                self._staging_seq += 1
                self._src_cond.notify()
        except Exception as e:
            print(f"frame publish failed: {e}")
            return

        self.publish_ms = (time.monotonic() - now) * 1000

    # ---- encoder side -----------------------------------------------------

    def _encode_loop(self):
        work = None
        scaled = None
        scaled_size = None

        while True:
            with self._src_cond:
                while self._staging_seq == self._encoded_seq:
                    self._src_cond.wait()
                if work is None or work.get_size() != self._staging.get_size():
                    work = pygame.Surface(self._staging.get_size(), 0,
                                          self._staging)
                work.blit(self._staging, (0, 0))
                self._encoded_seq = self._staging_seq

            started = time.monotonic()
            try:
                size = self._target_size(work.get_size())
                if size == work.get_size():
                    source = work
                else:
                    if scaled_size != size:
                        scaled_size = size
                        scaled = pygame.Surface(size)
                    scaler = pygame.transform.smoothscale if self.smooth \
                        else pygame.transform.scale
                    scaler(work, size, scaled)
                    source = scaled

                buf = io.BytesIO()
                pygame.image.save(source, buf, "frame.jpg")
                payload = buf.getvalue()
            except Exception as e:
                print(f"frame encode failed: {e}")
                time.sleep(0.5)
                continue

            self.encode_ms = (time.monotonic() - started) * 1000

            with self._out_cond:
                self._jpeg = payload
                self._seq += 1
                self._out_cond.notify_all()

    # ---- viewer side ------------------------------------------------------

    def latest(self, timeout=3.0):
        """Newest frame, waiting briefly if none has been encoded yet."""
        with self._out_cond:
            if self._jpeg is None:
                self._out_cond.wait(timeout)
            return self._jpeg

    def frames(self, boundary=b"eyesyframe"):
        """Generator of multipart chunks, one per new frame."""
        last_seq = 0
        while True:
            with self._out_cond:
                if self._seq == last_seq:
                    # a timeout rather than a plain wait, so a client that goes
                    # away while the engine is stalled still gets collected
                    self._out_cond.wait(2.0)
                    if self._seq == last_seq:
                        continue
                # skipping straight to the newest is the point: a slow viewer
                # drops frames instead of falling further behind
                last_seq = self._seq
                payload = self._jpeg

            yield (b"--" + boundary + b"\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Content-Length: " + str(len(payload)).encode()
                   + b"\r\n\r\n" + payload + b"\r\n")
