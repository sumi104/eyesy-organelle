# EYESY on Organelle S

EYESY OS 3.1 adapted to the Organelle S front panel. The base system, audio
driver and boot configuration are the same as `platforms/eyesy_cm3` — the CM3
carrier boards are near identical — so only the control surface differs.

## What is different from eyesy_cm3

| | eyesy_cm3 | organelle_s |
|---|---|---|
| ADC order | `adcRead(4,2,0,1,3)` | `adcRead(0..5)` = knob 1-4, volume, expression |
| Keys sent | lowest 10, reordered by a lookup table | all 25 raw, `0` = AUX, `1-24` = keyboard from low C |
| Encoder | simplified edge detect | Organelle quadrature table, 2 detents per pulse |
| OLED | not driven | 6 pages, encoder switches them |
| Foot switch | polled, unused | sent as key `25`, saves a scene or fires the trigger |

The knob that plays the fifth mode parameter is the **volume knob**. The
Organelle applies volume in software, so on EYESY it is free to use as a
control.

## How it is put together

Two processes, both started by systemd, talking OSC over UDP loopback. The C++
side reads pins and sends numbers; it does not know what any of them mean.
Deciding that is the engine's job, which is why changing an assignment needs no
rebuild. It is also why the display keeps working while the engine is loading a
mode: the frame buffer and the page state live on the C++ side, and the engine
only sends it what to say.

A third joins them while an Ableton Link trigger source is selected: `linkd`,
started and stopped by the engine, reporting the beat on the same loopback.
It is separate because Link is GPL and this tree is BSD — see
[linkd/README.md](linkd/README.md).

```mermaid
flowchart LR
    subgraph panel ["Front panel, read"]
        knobs["Knobs 1-4<br/>and volume"]
        keys["24 keys<br/>and AUX"]
        enc["Encoder"]
    end

    ctl["eyesyhw, C++<br/>hw_controls/controls<br/><br/>reads pins every 2 ms<br/>owns the frame buffer<br/>and the page state"]

    subgraph py ["eyesypy, Python, engines/python"]
        osc["osc.py"]
        org["organelle.py<br/>what a key means"]
        eng["eyesy.py<br/>state and scenes"]
        old["oled.py<br/>sends /oled/state at 20 Hz"]
        drw["main.py<br/>30 fps"]
    end

    lnk["linkd<br/>only while a Link<br/>trigger source is picked"]

    oled["OLED on the front panel<br/>128 x 64"]
    out["HDMI or composite<br/>1280 x 720"]

    knobs -- "SPI1, MCP3008" --> ctl
    keys -- "GPIO, 74HC165" --> ctl
    enc -- "same shift register" --> ctl
    ctl -- "SPI0, 1 KB frame" --> oled

    ctl <-- "UDP 4000 out, /knobs /key /encoder/turn<br/>UDP 4001 back, /oled/state /oled/text /led" --> osc

    lnk -- "UDP 4000<br/>/link/trig /link/status" --> osc

    osc --> org --> eng --> drw --> out
    eng --> old
```

Which half a change lands in decides what has to be run on the device:

| Changed | Needed |
|---|---|
| `engines/python/`, `web/` | `sudo systemctl restart eyesypy` |
| `platforms/organelle_s/hw_controls/` | `install.sh`, which rebuilds |
| `platforms/organelle_s/rootfs/` | `install.sh`, which deploys |

## Control map

Hold **C#** for the shifted layer.

| Key | Plain | With C# held |
|---|---|---|
| AUX | OSD on / off | System menu |
| C# | Shift | — |
| D# | Persist (auto clear off) | Knob sequencer: arm / record / play |
| C | Mode − | Foreground palette − |
| D | Mode + | Foreground palette + |
| E | Scene − | Background palette − |
| F | Scene + | Background palette + |
| G | Save scene (hold to delete) | Update current scene |
| A | Screen grab | Knob sequence play / stop |
| B | Trigger (hold for test tone) | Knob sequence record |
| F# | Audio input mute | Freeze the picture |
| G# | MIDI clock mute | MIDI note mute |
| A# | Auto random: off, then modes, then scenes, then off | — |
| Upper octave `C` / `D` | Wobble the foreground / background palette, tap again to stop | — |
| Upper octave `E` | MIDI channel +1, wrapping at 16 | — |
| Upper octave `F` `G` `A` `B` | — | — |
| Upper octave black keys | Wobble knob 1 to 5, tap again to stop. Hold and turn that knob for its depth | — |
| Foot switch | Save scene, or the same as `B` — Settings > System picks which | Knob sequence arm / disarm, when set to Trigger |

Shift + knob 1 still sets the input gain, as on EYESY. Shift + knob 5 — the
one the panel prints **Volume** on — sets the audio thru level, see below.

**Foot Switch** in Settings > System says which of the two it does. It saves
by default, which is what it did before there was a choice.

Saving goes straight to `save_scene()` rather than through the save key, which
deletes the current scene when it is held for a second — which is what a foot
resting on a pedal looks like. Deleting stays on `G`.

Set to Trigger a plain press **is** the `B` key: it goes through that key's own
handler rather than a copy of part of it, so it fires the trigger, plays the
test tone while held, and repeats after about a third of a second, exactly as
the key does.

Shift and the pedal arm the knob sequencer, and disarm it next time. That one
does not go through `B`: holding key 10 down is what starts the test tone and
the repeat, and neither belongs on a pedal being used to arm a recorder.

Which of the two jobs the pedal has gets latched when it goes down, and the
**Foot Switch** row stops responding while the pedal or `B` is held, saying so
on screen. Letting the setting move under a press already in flight is how the
test tone ends up playing with no way back.

## Palette wobble

Upper octave `C` picks a new foreground palette every so often, `D` does the
same for the background, and pressing the key again stops it. Each switches on
with a change rather than waiting out a cycle first, so the key has something
to show for itself, and neither ever picks the palette already showing.

**It runs on the Auto Random Cycle clock, not on the trigger.** This is the one
way it is unlike the knob wobble, and the difference is the point: a palette
that changed on every kick drum would be a strobe rather than a colour scheme.
It does not need the `A#` picker switched on — it borrows that setting's
interval, not the feature.

The two run on separate clocks. Started at different moments they change at
different moments, which is what you want; one clock would make the whole
picture blink at once.

Scenes carry it, the same way they carry the knob wobble. A scene also stores
the palette numbers that were showing, and recalling one with the wobble on
will move off them within a cycle — which is exactly what the knobs do too. A
scene saved before this existed loads with both off.

The `MOD` page of the OLED has a lamp for each, and switching one says on
screen how often it will move. There is deliberately no letter for it in the
top bar; see [OLED](#oled).

## MIDI channel

Upper octave `E` steps the MIDI channel by one, wrapping from 16 back to 1, and
says the new number on screen. It is also on **Settings → Audio MIDI Settings**,
which is where it was before it had a key.

**It steps on the way up, not the way down, and holding it does nothing.** The
other repeating keys here fire every frame once they start, which would run 1
to 16 in about half a second and make landing on a channel a matter of luck. A
key leaned on cannot walk the channel away from you.

It works with a menu open too, since it is a setting rather than a performance
control, and the MIDI page is where you would be looking while you set it. Each
press is written to `config.json`.

## Auto random

`A#` steps a picker through off, picking modes at random, picking scenes at
random, and off again. It moves the moment it is switched on rather than
leaving you wondering whether the key did anything, and it never picks what is
already playing, which would look the same as nothing happening.

How long it waits is set on **Settings → System** as **Auto Random Cycle**: 15,
30, 50 or 60 seconds, or `Random`, which draws a fresh interval between 15 and
60 seconds each time. The same setting times the palette wobble above, so it is
the one dial for how restless the instrument is. `M` or `S` in the top bar of
the OLED says the picker is running and which of the two it is picking.

It holds still while a menu is open, so it cannot change the mode out from
under someone reading a settings page. Picking scenes with none saved does
nothing and says so.

## Knob modulation

Each black key of the upper octave wobbles the knob above it — C# is knob 1
through to A# for knob 5. Tap it to start, tap again to stop.

**The movement is timed by whatever is driving the visuals.** Each trigger
picks somewhere new for the offset to head for and it glides there, and since
audio, MIDI notes, MIDI clock and Ableton Link all arrive as the same trigger,
the wobble follows whichever one is selected under Trigger Source. With
nothing triggering it settles on its last target and stays there, so muting
the audio with `F#` or the clock with `G#` stops it rather than leaving it
running on a clock of its own.

It rides on top of the position rather than sweeping the whole range. Scenes
store the set position, not wherever the wobble happened to be.

**While a knob is modulating it stops setting a value and shapes the wobble
instead**: turn it for the rate, or hold its own black key and turn it for the
depth. So the key that owns a knob's modulation is also what adjusts it — no
other modifier is involved, and shift on knob 1 is still the audio gain. The
OLED shows a bar for whichever one is moving, and each knob keeps its own pair.

Because the key doubles as a modifier it acts on release, and only when it was
tapped: holding it while turning its knob adjusts the depth and leaves the
modulation running.

The knob sequencer and the wobble both write the same five knobs, so they do
not run together. Starting a wobble while the sequence is playing — `Q` in the
top bar — is refused, and the key says why. Starting the sequence drops any
wobble that was running, which is also what happens when a scene carrying both
is recalled. Switching a running wobble off is always allowed.

Rate is how quickly the offset reaches each new target, on an exponential
curve so the slow end is not all crammed into the first millimetre of travel.
Turned up, the wobble lands on the beat and waits there; turned down it is
still travelling when the next one arrives. To move the centre position,
switch modulation off, set it, and switch back on.

Both take over smoothly: nothing changes until the knob has moved a little
from where it was, so a knob left at one end does not slam the value across
the moment it starts controlling something new. Switching modulation off
leaves the value where it was rather than snapping it to wherever the knob
ended up.

Scenes carry all of it: which knobs were wobbling and the rate and depth each
one had. A scene saved before this existed simply has nothing wobbling.

`config.json` holds the starting point for all five:

| | default | |
|---|---|---|
| `knob_mod_depth` | 0.25 | how far either side of the knob it can swing |
| `knob_mod_rate` | 0.15 | how quickly it reaches each target |
| `knob_mod_sync` | true | step on the trigger; false brings back a wobble that keeps its own time. Also on **Settings → Audio MIDI Settings** |

## Audio thru

The Organelle has an audio output and EYESY has nothing to play through it, so
**Audio In goes straight to Audio Out**. Hold shift and turn knob 5 to set how
loud, from silent to a little above unity. The OLED shows a bar while it moves,
the same one the modulation controls use, and the level is saved when shift
comes up.

It starts at silent, so this does nothing at all until the knob is turned.

**It costs no CPU.** The signal never reaches the CPU: the WM8731 has an
analogue path from its line input to its output mixer, inside the chip, and
all the engine does is close that switch once at startup. No samples are
copied, no thread runs, and the frame rate never sees it. There is no
conversion either, so the passthrough is not resampled to the 32kHz the
analysis runs at and adds no latency.

Reading the capture stream back out through a playback stream would have put
the audio in the same place as the drawing, where one late frame is a click.
That is the version this replaces, and why the answer to "how much does it
cost" is nothing rather than a number.

There is no on/off switch because zero on the knob is the codec's own mute.
The knob has to be moved a little before it takes hold, so pressing shift
never jumps the level to wherever knob 5 was left sitting.

**Knob 5 hands itself back to the mode where you leave it.** It is a mode
parameter the rest of the time, and letting go of shift gives it to the mode at
its new position rather than the one it had. Shift on knob 1 has always done
this with the gain; setting the level here is the same thing on knob 5. Put the
knob back before letting go if that parameter was somewhere you wanted it.

**The headphone jack follows the knob, the 1/4in outputs do not.** They are
different pins on the codec. The level control lives inside the headphone
amplifier, and the 1/4in outputs are taken from the output mixer ahead of it,
so they carry the passthrough at a fixed line level however the knob is set —
and they do not get the +6dB at the top of it either. Whatever is downstream is
expected to have its own level, which is what makes knob 5 a monitoring
control.

The stock Organelle is not like this because Pd scales the samples before they
reach the DAC, which is ahead of both jacks. Nothing here goes near the DAC,
which is the whole reason it is free.

There is one other gain stage in the path, the input PGA — `Capture Volume` in
ALSA — and it was measured to reach both jacks, so it would have made the 1/4in
outputs adjustable. It is deliberately left alone. It also feeds the ADC, so
turning the monitor down would take the visuals with it, and not gently: at the
bottom of its range the signal drops by a factor of 53, which even the largest
software gain the engine offers cannot lift back over the audio trigger
threshold. Turning down the monitor would stop the picture moving.

The output amp is the level control, which nothing else uses. The input gain
(shift + knob 1) is a software multiplier applied to the analysis only, so the
two do not interact: turning the visuals up does not turn the monitor up.

| | default | |
|---|---|---|
| `audio_thru_volume` | 0.0 | 0 is muted, 1 is +6dB. The knob spans -60dB to +6dB above zero |

## Ableton Link

Pick one of the **Link** entries under **Settings → Audio MIDI Settings →
Trigger Source** and the visuals follow the beat of anything else on the
network — Live, an iPad, another Organelle. There is no separate on switch:
Link runs exactly while a Link trigger source is selected. `G#` mutes it, the
same key that mutes the MIDI clock, and the MIDI page says which clock is
driving and how many peers it can see.

Link is a separate program here, because it is GPL and this tree is BSD, so
its source is not in this repository and has to be cloned to `~/link` before
`install.sh` will build it — see [Build and install](#build-and-install) and
[linkd/README.md](linkd/README.md). Until that is done the Link trigger
sources are selectable but nothing answers, and the MIDI page says `Link off`.

A trigger lands on the next frame, so it can be up to 33 ms late. That is true
of the MIDI clock sources too. It is enough to lock visuals to a beat and not
enough to call it sample accurate.

## OLED

The hardware process owns the frame buffer and the page state so the display
keeps working while the video engine is loading modes or restarting. The engine
pushes it state over OSC; see `engines/python/oled.py` and `OledPages.cpp`.

Turn the encoder to page. Pressing it switches whatever on/off setting the
page in front of you owns, and does nothing on the pages that have none — a
dot next to the page number marks the ones that respond.

| | Page | Press |
|---|---|---|
| 1 | **PERFORM** — mode, scene, five knob positions, stereo VU, input gain | — |
| 2 | **STATUS** — wifi network, IP address, resolution, frame rate, version | — |
| 3 | **MIDI** — channel, knob CCs, trigger source, input device, and whichever clock is driving: MIDI, or the Link tempo and peer count | — |
| 4 | **MOD** — knob modulation lamps, the two palette wobble lamps, and the MIDI channel | — |
| 5 | **LIVE** — video stream state and the address to watch it at | Stream on / off |
| 6 | **CONTROLS** — the key map above, in short form | — |

Pages declare their setting by name in `OledPages::toggleAction()`, and
`osc.py` maps the name to the action, so wiring a switch to another page is
two lines.

**A mode or scene name too long for its line slides through it** rather than
being cut off at the right hand edge. It holds at the start for a second and a
half, steps left two characters a second, holds again with the last character
on screen, and goes back to the beginning. `12/57 ` and `S 2/8 ` stay put — the
numbers are read at a glance and the names are what run off the end. Changing
mode or scene, or leaving the page and coming back, starts from the left again.

The two lines keep their own clocks. They are usually different lengths, so a
shared one would reach the end of the short name first and they would come
apart at the holds regardless; a name short enough to fit simply sits still.

Wrapping was the alternative, and neither line has anywhere to move down to.
Nothing else on the page can shift either, so the names move instead.

It costs nothing to run. The engine pushes `/oled/state` every 50ms and that
marks the page dirty, so the display is already being redrawn and shipped over
SPI twenty times a second whatever the names are doing; each line adds a
counter and an offset into a string.

Letters in the top bar: `X` audio muted, `K` clock muted, `N` notes muted,
`F` frozen, `P` persist, `M` auto random picking modes, `S` auto random
picking scenes, `r` sequencer armed, `R` recording, `Q` sequence playing,
`^` shift held.

Eight fit before the wifi icon and eight is as many as can be set at once,
since `M` and `S` are the two things the picker can be doing and only one of
them is ever true. They are still written in the order they would be given up,
`^` first, being the only one you are holding down while you read it. The
eighth slot came from retiring `MODE KEYS`: at nine characters it was the
longest page name and it cost a letter.

**The palette wobble has no letter here on purpose.** It follows the knob
wobble instead — a lamp on the `MOD` page and a message when it is switched —
which is what keeps this row from growing every time something new can be
switched on.

Audio mute is `X` and shift is `^` because the auto picker wanted `M` and `S`
to say which of the two things it is picking, and one letter meaning two
things is worse than a letter that has to be learned.

On PERFORM the five bars are the knobs in panel order, knob 1 to 4 then
volume, and `L` `R` `G` are the input meters and the gain. A dot over a bar
means that knob is being wobbled — the same filled circle the MOD page uses, and
drawn only for the knobs it applies to, so the usual case stays quiet.

The thin bar blinking under the meters is the trigger, the same thing the
yellow square shows in the video OSD — what makes it fire is the `Trig`
setting on the MIDI page.
A trigger only lasts one frame, so it is latched between display refreshes
rather than being missed.

The LIVE page is the quickest way to get the video onto a laptop mid set:
page to it, press the encoder, and the address shown is what to open in a
browser. See `web/STREAMING.md`.

### Messages

Pressing a key that changes something puts a message over the current page for
a second. Both lines are the small font: the second one carries the mode name,
the scene name, the reason — the half you are actually reading for — so making
the first one big only made the important half the harder one to read.

A reversed marker at the start says which kind it is, the same reversed block
the key names wear:

| Mark | Means | Example |
|---|---|---|
| `i` | it happened | `i Scene saved` / `scene-0004` |
| `!` | it did not | `! Modulation` / `knob seq is playing` |

Warnings stay up about twice as long, since a refusal has to be read to be any
use and a confirmation does not. Send them with `oled.warn()` instead of
`oled.notify()` — that is the whole difference at the call site.

The message is drawn over the page rather than instead of it, so a second of
message does not cost you your place. Line one fits 18 characters next to the
marker, line two fits 20 across the full width.

### Working on the layout without the device

`tools/oled_preview.cpp` renders every page to a raw frame buffer dump and
`tools/oled_view.py` turns those into a PNG, so layout changes can be checked
on a laptop:

    make -f tools/Makefile
    ./oled_preview /tmp/oled
    python3 tools/oled_view.py /tmp/oled*.raw -o /tmp/oled.png

A contact sheet says whether a layout is right and nothing about whether a
speed is. `tools/oled_anim.cpp` covers the other half: it ticks the same
`OledPages` on the same 50ms clock `main.cpp` uses and dumps a frame per
refresh, and `--html` plays them back at that interval in a self-contained page
with no dependencies. So the scroll can be watched at its real speed, and any
constant that governs it argued about, before anything is flashed.

    make -f tools/Makefile oled_anim
    ./oled_anim /tmp/anim
    python3 tools/oled_view.py --html /tmp/anim.html /tmp/anim*.raw

`oled_anim` takes the mode name as a second argument and the scene name as a
third, so the awkward lengths — one character over the line, twice the line,
one of each — can be tried directly.

    ./oled_anim /tmp/anim "a very long mode name" "a very long scene name"

The Makefile points clang at the SDK when `uname` says Darwin, so a bare `make`
works on a Mac as well as on the device. Without it MacPorts' `g++` is found
first and the build dies on `<string>`.

## Build and install

Unlike `eyesy_cm3`, the built `controls` binary is **not** committed here — it
is gitignored and has to be built on the device. A prebuilt one would be an
EYESY binary sitting where the Organelle binary belongs, and a stale one runs
with the wrong ADC order and key map without complaining. If `eyesyhw.service`
fails with "no such file", the build step below has not been run.

**For Ableton Link, clone it first.** `install.sh` builds `linkd` only if the
headers are already there, so doing this afterwards means running `install.sh`
again. Skip it and everything else still works, Link included in the trigger
source list but reporting nothing.

    git clone --recurse-submodules https://github.com/Ableton/link ~/link

`--recurse-submodules` is not optional: the asio it needs to build is a
submodule, and without it the compile fails on a missing header.

Then, as the `music` user — not with sudo, or the build output ends up owned by
root and the next `git pull` trips over it:

    ~/EYESY_OS/platforms/organelle_s/install.sh

That remounts `/` writable, builds `controls`, builds `linkd` if `~/link` is
there and says it is skipping it if not, runs `deploy.sh` and restarts the
services. `/` is left writable, so reboot before pulling the plug.

`deploy.sh` installs the systemd units from `rootfs/`, which point at this
platform directory and set `EYESY_PLATFORM=organelle_s` for the video engine.
That environment variable is what selects the Organelle key mapping — without
it the engine behaves exactly like stock EYESY.

### Getting the code onto the device

The changes are not confined to this directory: `engines/python` and `web`
change too, and the C++ here sends raw key indices that only the new engine
understands. Copying just `platforms/organelle_s` across leaves the keyboard
worse than stock, so move the whole tree.

The device's `origin` is the upstream repo, which does not have this branch.
Add your own fork as a second remote once:

    sudo mount -o remount,rw /
    cd ~/EYESY_OS
    git remote add s <your fork url>
    git fetch s
    git checkout -b organelle-s s/organelle-s

After that each round trip is two lines:

    cd ~/EYESY_OS && git pull s organelle-s
    platforms/organelle_s/install.sh

## Checking the mapping

The front panel mapping and the stream settings have unit tests that need no
hardware:

    cd ~/EYESY_OS/engines/python
    python3 -m unittest discover -s tests -v
