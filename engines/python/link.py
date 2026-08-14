"""Follows an Ableton Link session, through the linkd helper process.

Link is GPL and this tree is BSD, so it stays a separate program that is talked
to rather than linked against. See platforms/organelle_s/linkd. This module
starts it, tells it which division to report, and keeps what it says back.

There is no separate on switch. Link is running exactly when one of the Link
trigger sources is selected, so there is no second piece of state to get out of
step with the first.
"""

import ctypes
import os
import signal
import subprocess

# trigger source index -> beats between triggers
DIVISIONS = {7: 0.25, 8: 0.5, 9: 1.0, 10: 4.0}

# what linkd reports back
running = False
peers = 0
tempo = 0.0

_proc = None
_missing_logged = False


def binary_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(
        os.path.join(here, "..", "..", "platforms", "organelle_s", "linkd", "linkd"))


def is_link_source(eyesy):
    return eyesy.config.get("trigger_source") in DIVISIONS


def division(eyesy):
    return DIVISIONS.get(eyesy.config.get("trigger_source"), 1.0)


def _die_with_parent():
    """So a hand started engine does not leave linkd behind."""
    try:
        PR_SET_PDEATHSIG = 1
        ctypes.CDLL("libc.so.6").prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
    except Exception:
        pass


def apply(eyesy):
    """Start or stop linkd to match the trigger source. Safe to call often."""
    global _proc, _missing_logged, running, peers, tempo

    import osc

    if is_link_source(eyesy):
        if _proc is None or _proc.poll() is not None:
            path = binary_path()
            if not os.path.exists(path):
                if not _missing_logged:
                    _missing_logged = True
                    print(f"link: {path} is not built, see its README")
                return
            try:
                _proc = subprocess.Popen([path], preexec_fn=_die_with_parent)
                print("link: started linkd")
            except Exception as e:
                print(f"link: could not start linkd: {e}")
                return
        osc.send_link("/link/enable", 1)
        osc.send_link("/link/div", float(division(eyesy)))
    else:
        if _proc is not None and _proc.poll() is None:
            osc.send_link("/link/enable", 0)
        close()


def status(enabled_flag, peer_count, tempo_value):
    """Called from osc.py when linkd reports in."""
    global running, peers, tempo
    running = bool(enabled_flag)
    peers = int(peer_count)
    tempo = float(tempo_value)


def close():
    global _proc, running, peers, tempo

    running = False
    peers = 0
    tempo = 0.0

    if _proc is None:
        return
    if _proc.poll() is None:
        print("link: stopping linkd")
        _proc.terminate()
        try:
            _proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            _proc.kill()
    _proc = None


def describe():
    """One short line for the OLED."""
    if not running:
        return "Link off"
    if peers == 0:
        return f"Link {tempo:.1f} alone"
    return f"Link {tempo:.1f} {peers} peer" + ("s" if peers != 1 else "")
