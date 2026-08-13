"""Mac audio input for the simulator, shaped exactly like the instrument's.

engines/python/sound.py is ALSA only, so this is the CoreAudio half. What
matters is not that it reads audio but that it hands the engine the *same
numbers*: eyesy.audio_in is what every mode draws, so if the shape of it
differs from the instrument the simulation is worthless.

The instrument reads 32kHz stereo int16 and averages every 16 samples into a
100 entry ring buffer. Sixteen samples at 32kHz is a 0.5ms window, and the ring
holds 50ms. A Mac input runs at whatever rate it likes, usually 48kHz, so the
block is sized by time rather than by sample count and the window comes out the
same. The values stay in int16 range, unsmoothed, with the gain applied before
clamping, because that is what sound.py does.

Peak follows the same rule too: the running maximum is committed once per trip
around the ring and reset, which is what main.py compares against 20000 to fire
the audio trigger.
"""

import threading

import numpy as np
import sounddevice as sd

BUFFER_SIZE = 100

# what the instrument's sound card runs at, kept as the reference for the
# averaging window rather than as a rate to request from CoreAudio
DEVICE_RATE = 32000
DEVICE_BLOCK = 16


def list_input_devices():
    """[(index, name, channels, samplerate)] for everything that can record."""
    devices = []
    try:
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                devices.append({
                    "index": i,
                    "name": d["name"],
                    "channels": d["max_input_channels"],
                    "samplerate": int(d["default_samplerate"]),
                })
    except Exception as e:
        print(f"could not list audio devices: {e}")
    return devices


def default_input_device():
    try:
        index = sd.default.device[0]
        return None if index is None or index < 0 else index
    except Exception:
        return None


class AudioInput:
    """Fills two ring buffers the render loop copies out of, once a frame.

    The stream callback runs on a CoreAudio thread, so the buffers are handled
    under a lock, the same way the instrument does across its process
    boundary.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.buffer = [0.0] * BUFFER_SIZE
        self.buffer_r = [0.0] * BUFFER_SIZE
        self.peak = 0.0
        self.peak_r = 0.0

        # set by the render loop every frame from config["audio_gain"], the
        # same mapping the instrument uses
        self.gain = 1.0

        self.device = None
        self.device_name = ""
        self.samplerate = 0
        self.block = DEVICE_BLOCK
        self.error = ""

        self._stream = None
        self._write_index = 0
        self._max_peak = 0.0
        self._max_peak_r = 0.0
        self._tail = None

    @property
    def running(self):
        return self._stream is not None and self._stream.active

    def start(self, device=None):
        """Open an input. Returns True on success, otherwise check .error.

        The first call is what triggers the microphone permission prompt, and
        macOS attributes it to whichever app launched python.
        """
        self.stop()
        self.error = ""

        if device is None:
            device = default_input_device()
        if device is None:
            self.error = "no audio input device"
            return False

        try:
            info = sd.query_devices(device)
        except Exception as e:
            self.error = f"no such audio device {device}: {e}"
            return False

        if info["max_input_channels"] < 1:
            self.error = f"{info['name']} has no input channels"
            return False

        rate = int(info["default_samplerate"])
        channels = min(2, int(info["max_input_channels"]))

        # a block of the same duration as the instrument's sixteen samples at
        # 32kHz, so audio_in covers the same 50ms whatever the Mac runs at
        block = max(1, round(DEVICE_BLOCK * rate / DEVICE_RATE))

        with self.lock:
            self.buffer = [0.0] * BUFFER_SIZE
            self.buffer_r = [0.0] * BUFFER_SIZE
            self.peak = 0.0
            self.peak_r = 0.0
            self._write_index = 0
            self._max_peak = 0.0
            self._max_peak_r = 0.0
            self._tail = None

        self.block = block

        try:
            self._stream = sd.InputStream(
                device=device,
                channels=channels,
                samplerate=rate,
                dtype="int16",
                blocksize=0,
                latency="low",
                callback=self._callback)
            self._stream.start()
        except Exception as e:
            self._stream = None
            self.error = str(e)
            print(f"could not open audio input: {e}")
            return False

        self.device = device
        self.device_name = info["name"]
        self.samplerate = rate
        print(f"audio in: {info['name']} {rate}Hz {channels}ch, "
              f"averaging {block} samples per value")
        return True

    def stop(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _callback(self, indata, frames, time_info, status):
        if status:
            # overflows are normal when the machine is busy, not worth a line
            # every time
            pass

        data = indata if self._tail is None or len(self._tail) == 0 \
            else np.concatenate((self._tail, indata))

        usable = (len(data) // self.block) * self.block
        self._tail = data[usable:].copy()
        if usable == 0:
            return

        # one average per block, per channel
        avg = data[:usable].astype(np.float32) \
            .reshape(-1, self.block, data.shape[1]).mean(axis=1)
        avg *= self.gain
        np.clip(avg, -32768, 32767, out=avg)

        left = avg[:, 0]
        right = avg[:, 1] if avg.shape[1] > 1 else left

        with self.lock:
            index = self._write_index
            max_peak = self._max_peak
            max_peak_r = self._max_peak_r

            for i in range(len(left)):
                l = float(left[i])
                r = float(right[i])
                self.buffer[index] = l
                self.buffer_r[index] = r
                if l > max_peak:
                    max_peak = l
                if r > max_peak_r:
                    max_peak_r = r
                index = (index + 1) % BUFFER_SIZE
                # committed once per trip round the ring, as on the instrument
                if index == 0:
                    self.peak = max_peak
                    self.peak_r = max_peak_r
                    max_peak = 0.0
                    max_peak_r = 0.0

            self._write_index = index
            self._max_peak = max_peak
            self._max_peak_r = max_peak_r
