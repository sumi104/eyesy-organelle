# EYESY_OS

The operating system for the EYESY video synthesizer device.

* engines, generally a video engine takes audio, midi, and control messages as input and outputs video
* web, a web based editor and file manager

The macOS mode simulator that used to live in `desktop/` is now its own
repository, `EYESY_Simulator`. It imports `engines/python` from a checkout of
this one, so it expects the two side by side, or `EYESY_OS_ROOT` pointing here.
