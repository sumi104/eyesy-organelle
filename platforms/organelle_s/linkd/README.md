# linkd

Follows an Ableton Link session and tells the video engine when a beat division
goes by, so the visuals can be triggered from whatever else is on the network.

## Why it is a separate program

**Ableton Link is GPL. The rest of this tree is BSD 3-Clause.** Compiling Link
into `hw_controls/controls` would make that binary GPL too, and with it any
chance of the Organelle work going back to Critter & Guitari.

So Link lives here on its own, and the only thing crossing the boundary is an
OSC message. Nothing in this directory is linked into the rest of the system,
and nothing from the rest of the system is linked in here — the OSC encoding in
`linkd.cpp` is written out by hand rather than reusing the copy in
`hw_controls/OSC` for exactly that reason.

`linkd` itself is GPL, in `LICENSE`.

## Building it

The Link headers are not vendored. Clone them once:

    git clone --recurse-submodules https://github.com/Ableton/link ~/link

Then:

    make

`install.sh` in the parent directory builds it when the headers are there and
says so when they are not, so a system without them keeps working with
everything except Link.

**Link needs C++17.** It used to build as C++11 and a lot of writing about it
still says so, but the current version uses `std::invoke_result_t`. The
Makefile asks for C++17; GCC on Raspberry Pi OS Bookworm is fine with it.

## Talking to it

Sends to the video engine on port 4000:

| | |
|---|---|
| `/link/trig` | a beat division boundary was crossed |
| `/link/status i i f` | enabled, peer count, tempo — four times a second |

Listens on port 4002:

| | |
|---|---|
| `/link/enable i` | join or leave the session |
| `/link/div f` | beats between triggers, `0.25` is a sixteenth |

The engine starts and stops it, and there is no separate on switch: Link runs
exactly while one of the Link trigger sources is selected in
**Settings → Audio MIDI Settings → Trigger Source**. One piece of state, so
there is no second one to get out of step with it.

## What to expect

The engine draws at 30 fps, so a trigger lands on the next frame boundary and
is up to 33 ms late. That is true of the MIDI clock sources as well and Link
does not change it — a sixteenth at 120 BPM is 125 ms, so it holds together,
but this is not sample accurate and cannot be.

Link finds its peers over UDP multicast. A network with AP isolation, which
guest wifi usually has, will show no peers however healthy everything else
looks.
