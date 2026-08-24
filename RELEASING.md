# Making a release

How an SD card image gets built and published. This is a maintainer's
document — if you are trying to *install* the thing, the front
[README](README.md) is where to start.

The card is the release. The source alone cannot build a working machine — the
codec needs a kernel that is not the stock one, and the overlay and
`config.txt` that go with it are installed by hand, not by any script here — so
what gets published is a card image, and the tag exists to say which commit is
inside it.

Work through this in order. Steps 1 to 3 happen on the instrument, 4 to 6 on
the Mac, 7 on GitHub.

---

## 1. Get the instrument onto the commit you are releasing

Whoever writes this image will want to be able to update it later, so the
checkout inside it has to point at somewhere they can reach.

    sudo ~/EYESY_OS/Tools/remount-rw.sh

**The remote must be an HTTPS URL.** If it is the `git@github.com:` form, no
one but you can pull from it — they have no key.

    cd ~/EYESY_OS
    git remote set-url s https://github.com/sumi104/eyesy-organelle.git
    git fetch s

**Track `master`, not `organelle-s`.** `master` only ever moves to something
that has been run on an instrument; `organelle-s` is where work lands and can
be mid-flight.

    git checkout -B master s/master
    git branch --set-upstream-to=s/master master

Build everything, so the card boots into a working panel rather than into a
missing binary:

    platforms/organelle_s/install.sh

**Ableton Link is a decision.** `install.sh` builds `linkd` only if `~/link` is
already there. With it, Link works out of the box; without it, the Link trigger
sources are selectable and report nothing. If you want it in the image, clone
it and run `install.sh` again:

    git clone --recurse-submodules https://github.com/Ableton/link ~/link

Check what you have:

    git remote -v && git status -sb && git log --oneline -1

`s` should be the HTTPS URL, and the branch line should read `## master...s/master`.

## 2. Take your own things out of it

**Everything on the card ships with it.** The one that matters is the WiFi
password: it is stored in the clear, and handing out a card with your home
network on it is the mistake to avoid here.

| | Where | How |
|---|---|---|
| **WiFi passwords** | `/sdcard/system-connections/` | Settings → System → Forget all WiFi networks |
| Settings | `/sdcard/System/config.json` | delete it; defaults are written on the next boot |
| Scenes | `/sdcard/Scenes/` | keep or delete, as you like |
| Screen grabs | `/sdcard/Grabs/` | delete — they are yours, and they are bulk |

Modes are the one thing worth leaving in. A card that boots with nothing to
draw is a poor first impression.

Confirm the WiFi is gone before going on:

    ls /sdcard/system-connections/

## 3. Shut it down cleanly

Put the filesystem back to read only first, or the image catches it mid-write:

    sudo ~/EYESY_OS/Tools/remount-ro.sh
    sudo shutdown -h now

Wait for it to stop, pull the power, take the card out.

## 4. Read the card

On the Mac, with the card in a reader. **Find the disk first and read the
output carefully** — the next command names a raw device, and naming the wrong
one is how a hard disk gets destroyed.

    diskutil list

Look for the one whose size matches the card and whose partitions look like a
Raspberry Pi's — a small `Windows_FAT_32` boot partition and a Linux one.
Suppose it is `/dev/disk4`.

    diskutil unmountDisk /dev/disk4

Read it. `rdisk` rather than `disk` is the raw device and is several times
faster:

    sudo dd if=/dev/rdisk4 of=~/eyesy-organelle.img bs=4m

macOS `dd` prints nothing while it works. **Press Ctrl-T** to make it say how
far along it is. A card takes a while — this is reading every byte of it,
including the empty ones.

## 5. Make it smaller

The image is the size of the card, empty space and all. An 8GB card gives an
8GB file whatever is on it.

**Compressing is the easy half:**

    gzip -9 ~/eyesy-organelle.img

How well that works depends on what the unused space contains. On a card that
has only ever held this, it is mostly zeros and compresses to very little; on
one that held something else first, the old data is still there and does not
compress at all. **If the result is disappointing, that is why** — writing
zeros over the free space before imaging fixes it, but that has to be done on
Linux, where the filesystem can be mounted read/write safely.

**Shrinking the partition** — cutting the image down to the space actually
used — needs Linux as well. `pishrink` is the usual tool. macOS cannot resize
an ext4 filesystem, so there is no way to do this step here.

Two ways round it, in order of how little work they are:

1. **Build the master image on a small card.** An 8GB card cannot produce an
   image bigger than 8GB. The card in the instrument does not have to be the
   large one you use day to day.
2. **Do the shrink on a Linux machine or a VM**, with `pishrink`, and bring the
   result back.

## 6. Write it to a different card and boot it

**Do not skip this.** Everything up to here is untested until a card written
from the image starts an instrument.

    diskutil unmountDisk /dev/disk4
    gunzip -c ~/eyesy-organelle.img.gz | sudo dd of=/dev/rdisk4 bs=4m

Then, on the instrument, with a monitor attached:

- [ ] It boots, and a mode is drawing
- [ ] The keys do what [the control map](platforms/organelle_s/MANUAL.md#control-map) says
- [ ] All seven OLED pages are there and the encoder pages through them
- [ ] Holding the encoder on SETTINGS restarts the video engine
- [ ] `SETTINGS` shows no WiFi network — **if it shows yours, start again at step 2**
- [ ] Settings → Controls exists and Battery is off
- [ ] Joining a network and pressing the knob on LIVE starts the stream
- [ ] `cd ~/EYESY_OS && git status -sb` says `## master...s/master`
- [ ] `git pull` works without asking for anything

## 7. Tag it and publish

Tag the commit the image was built from, **after** the image is made and
checked, so the two cannot drift:

    git tag -a organelle-0.9-rc1 -m "First image for Organelle M and S" master
    git push fork organelle-0.9-rc1

Name the file so it still says what it is when it is sitting alone in someone's
downloads folder:

    eyesy-organelle-0.9-rc1.img.gz

Then a GitHub Release on that tag, with the notes and a link to the image.
**GitHub caps an attached file at 2GB**, so an image over that has to be hosted
elsewhere and linked to rather than attached.

## Naming

Tags are `organelle-<version>`. The prefix keeps them apart from the upstream
tags that share this repository — `v3.1`, `EYESY_v3.1.img` and the rest are
Critter & Guitari's, and a bare `v3.2` here would both collide with their
numbering and read as though it were theirs.

Hyphens rather than the underscores upstream uses, for the same reason: the
two series should be tellable apart at a glance in one list.

`0.x` while this is still finding out what breaks on other people's
instruments. `-rc1` while a version is out for comment rather than settled.
