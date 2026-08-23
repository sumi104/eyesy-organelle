# EYESY OS for Organelle M and S

[EYESY](https://www.critterandguitari.com/eyesy) is Critter & Guitari's video
synthesiser: audio and MIDI go in, generated video comes out, and the picture
is made by small Python programs called **modes** that anyone can write.

The Organelle M/S are their Music Computer — different instrument, near enough
the same computer inside. This is EYESY OS made to run on one,
using the keyboard, the encoder and the OLED that the EYESY itself does not
have.

It is a fork of [EYESY_OS](https://github.com/critterandguitari/EYESY_OS).
Everything the EYESY does, it still does; the changes are the control surface
and what can be reached without a menu.

## What it adds

The EYESY has ten buttons, so most of what it can do sits behind holding one of
them. An Organelle has twenty five keys, an encoder and a screen, so most of it
does not have to.

- **The lower octave** is the EYESY panel: mode, scene, trigger, save, persist,
  screen grab, and the two mutes.
- **The upper octave** is colour. Two keys step the foreground palette, two
  step the background, and either pair pressed together sets that palette
  wandering on its own. One more steps the MIDI channel.
- **The black keys up there** each set one of the five knobs wandering — turn
  the knob for how fast, hold the key and turn it for how far.
- **Seven OLED pages**: what is playing, what the instrument is set to, MIDI,
  the live video stream, and the key map itself on the last two, so the panel
  explains itself. Holding the encoder on the settings page **restarts the
  video engine** — which works with no monitor plugged in, and when the engine
  is the thing that has stopped.
- **Audio in goes straight to audio out**, through the codec's own analogue
  path. It costs no CPU at all — see [the platform
  notes](platforms/organelle_s/README.md#audio-thru).
- **The foot switch** saves a scene or fires the trigger, whichever you pick.
- **A web page** to watch the video on another machine on the network.
- Ableton Link, an auto-random picker, a knob sequencer, and scenes that
  remember all of it.

The full control map and the reasoning behind it are in
**[platforms/organelle_s/README.md](platforms/organelle_s/README.md)**.

## Installing

**Use the SD card image.** Writing it to a card is the whole installation.

The source in this repository is not enough on its own to build a working
machine, and that is not an oversight. The audio codec is driven over SPI by a
kernel that is not the stock one, the device tree overlay that goes with it has
to be compiled and installed by hand, and `config.txt` has to match. What is
here — `platforms/organelle_s/dts/`, `platforms/organelle_s/boot/` — is the
record of what those are, not a script that installs them.

Once a machine is running, updating it **is** just the source:

    sudo ~/EYESY_OS/Tools/remount-rw.sh
    cd ~/EYESY_OS && git pull s organelle-s
    platforms/organelle_s/install.sh

`s` is whatever the remote pointing at this repository is called on that
machine. The remount is not optional — the root filesystem is read only, and
the pull has to write before `install.sh` gets a chance to remount it.

That rebuilds the hardware process and restarts the services. See
[Build and install](platforms/organelle_s/README.md#build-and-install) for the
one time remote setup and for Ableton Link, which has to be fetched separately
before it will build.

## Known limits

- **The Organelle M battery support has never been run on an M.** There is no M
  here to try it on. It is off by default and has to be switched on in
  Settings > Controls; the reading, the thresholds and the shutdown all follow
  Critter & Guitari's own `Organelle_OS`. On an S it is safe either way — the
  power pin reads mains there, so the shutdown cannot fire.
- **32 bit only.** The kernel patches that drive the WM8731 over SPI are not
  upstream, so there is no arm64 build.
- **Ableton Link's tempo and peer count are not displayed.** Link works and the
  selected source is shown; the numbers lost their row when the MIDI page was
  rearranged.
- Two upper octave keys, `A` and `B`, do nothing yet.
- The two keys of a palette pair have to go down together to count as a chord.
  Holding one and adding the other a second later steps the palette twice
  instead — by then the first key is scrolling.
- The hardware process is built on the device rather than committed, so a fresh
  checkout needs `install.sh` before the panel works.

## Layout

| | |
|---|---|
| `engines/python` | the video engine: modes, scenes, knobs, MIDI, audio analysis |
| `platforms/organelle_s` | the Organelle control surface, the OLED, and the notes on both |
| `platforms/eyesy_cm3` | the original EYESY hardware, left as it was |
| `web` | the browser based mode editor, file manager and video stream |
| `Tools` | remount the read only root filesystem read/write and back |

## Releases

The card image is built and published by hand; how, and what has to be taken
out of it first, is in [RELEASING.md](RELEASING.md).

## Licence and credit

EYESY OS is by Owen Osborn and Critter & Guitari, under the BSD 3-Clause
licence — see [LICENSE.txt](LICENSE.txt). This fork keeps it. The battery
handling follows their
[Organelle_OS](https://github.com/critterandguitari/Organelle_OS).

Ableton Link is GPL and therefore not in this tree. `linkd` is built from a
separate checkout, and everything works without it — see
[platforms/organelle_s/linkd/README.md](platforms/organelle_s/linkd/README.md).
