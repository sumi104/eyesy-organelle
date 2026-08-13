# EYESY mode simulator for macOS

Runs the instrument's video engine on a Mac against a folder of modes, and
puts the picture, the panel controls and a source editor in a browser. A mode
can be written, played against live audio and fixed without an EYESY on the
desk.

    http://127.0.0.1:8080/

The engine is used unmodified — `engines/python` is imported as it is, so what
you see here is what the instrument draws.

## Running it

```bash
EYESY_OS/desktop/run.sh
```

Run it from **Terminal.app** the first time. The microphone prompt is
attributed to whichever app started python, and only that app can be granted
access afterwards.

    --modes PATH   folder of mode folders (remembered after the first run)
    --port N       default 8080
    --window       also open a native pygame window
    --no-browser   do not open a browser on startup

Settings live in `~/.eyesy_sim/settings.json`. The engine's own config, screen
grabs and scenes go under `~/.eyesy_sim/` too, standing in for the instrument's
`/sdcard`, so nothing is written into the modes folder except mode source.

## Setting up

Needs **Python 3.11 or older** — `eyesy.py` imports `imp`, which was removed in
3.12.

```bash
/opt/local/bin/python3.11 -m venv .venv
.venv/bin/pip install pygame-ce flask sounddevice numpy psutil
```

`run.sh` expects that virtualenv two levels up from this folder, next to
`EYESY_OS`.

## Using it

The mode list is the folder's subdirectories. Modes whose `main.py` does not
import are listed in red with the reason on hover — clicking one opens it in
the editor rather than trying to play it, and saving a fix puts it straight
back into the rotation.

The ten panel buttons behave as they do on the instrument, and the number row
`1`-`9`,`0` does the same thing. Holding **SHIFT** (key 2) shows what each
button does with shift held.

| key | | with shift |
|---|---|---|
| 1 | OSD | settings menu |
| 2 | shift | |
| 3 | auto clear | |
| 4 / 5 | previous / next mode | previous / next foreground palette |
| 6 / 7 | previous / next scene | previous / next background palette |
| 8 | save scene | update scene |
| 9 | screen grab | knob sequencer play/stop |
| 10 | trigger | knob sequencer record |

Holding **TRIG** also replaces the input with the instrument's simulated tone,
so a mode can be checked with nothing playing.

**⌘S** in the editor saves and reloads the mode. Reload re-runs `setup()`, so a
mode that accumulates state in a global list will accumulate it again — the
same as reloading on the instrument.

## Audio

The gain and the trigger threshold work on the same numbers the instrument
uses. `sound.py` reads 32kHz stereo and averages every 16 samples into a 100
entry ring buffer — a 0.5ms window, 50ms of history. A Mac input runs at
whatever rate it likes, so `sim_audio.py` sizes its block by time instead
(24 samples at 48kHz) and `eyesy.audio_in` comes out the same shape. Without
that the modes would look different here than on the instrument, which would
make the whole thing pointless.

### Capturing Spotify, Music, QuickTime or Audacity

macOS will not let one app record another's output, so it has to go through a
virtual audio device. [BlackHole](https://existential.audio/blackhole/) is free
and installs from a .pkg:

1. Install BlackHole 2ch.
2. **Audio MIDI Setup → + → Create Multi-Output Device**, tick both BlackHole
   2ch and the built-in output, so you still hear it.
3. Make that multi-output device the system output.
4. Pick **BlackHole 2ch** in the simulator's audio input list.

Audacity can select BlackHole as its output directly. Everything else follows
the system output.

## How it is put together

    pygame render loop  ── main thread, because macOS insists ──┐
      1280x720, 30fps                                           │
            ▲                                                   ▼
      command queue                              sim_video.FrameStream
            │                                     ├─ staging blit  1.8ms
      Flask (daemon thread)                       └─ worker thread: scale + jpeg
            ▲                                                   │
            └────── browser ──▶ /stream.mjpg ◀──────────────────┘
            ▲
      sim_audio.AudioInput ◀── CoreAudio ◀── microphone or BlackHole

The instrument splits the encoder into its own process through `/dev/shm`.
macOS has no `/dev/shm`, so that collapses into `sim_video.py` — but the reason
for the split does not, because pygame's JPEG encoder costs 17ms at 640x360 on
an Intel Mac, half the frame budget. The render loop only blits into a staging
surface and a worker thread does the rest, so the stream size does not slow the
visuals down. `pub` and `enc` in the header are the two costs.

Nothing in the web thread writes engine state: it queues a callable that the
render loop runs between frames.

`stubs/liblo.py` exists so `eyesy.py` → `oled.py` → `osc.py` → `import liblo`
resolves, liblo being a C library the instrument has and a laptop does not.
`oled.py` is a no-op unless `EYESY_PLATFORM=organelle_s`, which the simulator
makes sure it is not.

## Known limits

- No MIDI. `midi.py` needs mido and is not started; MIDI note triggers and CC
  knob control are therefore unavailable.
- Editing a mode outside the browser needs **再スキャン** or a save from the
  editor; there is no file watcher.
- The settings menu's WiFi and hardware test pages are the instrument's and do
  nothing useful here.
- Video resolution changes from the settings menu take effect next launch
  rather than restarting the engine.
