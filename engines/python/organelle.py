"""Control mapping for the Organelle S front panel.

The hardware process on this platform sends raw key indices: 0 is the AUX
button, 1 to 24 are the keyboard starting at low C, and 25 is the pedal jack.
Everything here translates those into the ten EYESY panel buttons plus the
handful of controls that only exist on the Organelle.

Nothing in this module runs unless EYESY_PLATFORM=organelle_s, so the EYESY
hardware keeps its original behaviour.
"""

import os

import oled

# raw key indices from platforms/organelle_s/hw_controls
AUX = 0
FOOTSWITCH = 25

# lower octave, 1 is low C
KEY_C, KEY_CS, KEY_D, KEY_DS, KEY_E, KEY_F = 1, 2, 3, 4, 5, 6
KEY_FS, KEY_G, KEY_GS, KEY_A, KEY_AS, KEY_B = 7, 8, 9, 10, 11, 12

# upper octave, twelve assignable mode slots
UPPER_OCTAVE_FIRST = 13
NUM_MODE_SLOTS = 12

# names of the upper octave keys, index matches the mode slot
SLOT_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# organelle key -> eyesy panel button, see dispatch_key_event() in eyesy.py
EYESY_BUTTON = {
    AUX:        1,   # osd, with shift opens the menu
    KEY_CS:     2,   # shift
    KEY_DS:     3,   # persist
    KEY_C:      4,   # mode -,   with shift fg palette -
    KEY_D:      5,   # mode +,   with shift fg palette +
    KEY_E:      6,   # scene -,  with shift bg palette -
    KEY_F:      7,   # scene +,  with shift bg palette +
    KEY_G:      8,   # save scene, hold to delete, with shift updates it
    KEY_A:      9,   # screen grab, with shift plays / stops the knob sequence
    KEY_B:      10,  # trigger, with shift arms the knob sequence recorder
    FOOTSWITCH: 10,  # pedal doubles the trigger key
}


def is_organelle():
    return os.environ.get("EYESY_PLATFORM", "") == "organelle_s"


def slot_for_key(k):
    """Mode slot 0-11 for an upper octave key, or None."""
    slot = k - UPPER_OCTAVE_FIRST
    if 0 <= slot < NUM_MODE_SLOTS:
        return slot
    return None


def _recall_mode(eyesy, slot):
    name = eyesy.key_modes[slot]
    if not name:
        oled.notify(f"{SLOT_NAMES[slot]} empty")
        return
    try:
        eyesy.set_mode_by_name(name)
    except ValueError:
        print(f"key slot {slot} points at missing mode {name}")
        oled.notify(f"{name}?")
        return
    oled.notify(name)


def _assign_mode(eyesy, slot):
    eyesy.key_modes[slot] = eyesy.mode
    eyesy.config["key_modes"] = list(eyesy.key_modes)
    eyesy.save_config_file()
    oled.send_keymap(slot, eyesy.mode)
    oled.notify(f"{SLOT_NAMES[slot]}={eyesy.mode}")
    print(f"assigned mode {eyesy.mode} to key slot {slot}")


def dispatch_key(eyesy, k, v):
    """Called from osc.py for every raw organelle key event."""
    pressed = v > 0
    shift = eyesy.key2_status

    # the twelve keys of the upper octave recall modes, holding shift while
    # pressing one stores the mode that is playing right now
    slot = slot_for_key(k)
    if slot is not None:
        if pressed and not eyesy.menu_mode:
            if shift:
                _assign_mode(eyesy, slot)
            else:
                _recall_mode(eyesy, slot)
        return

    # controls that have no equivalent on the EYESY panel
    if k == KEY_FS:
        if pressed:
            if shift:
                eyesy.toggle_freeze()
            else:
                eyesy.toggle_audio_mute()
        return

    if k == KEY_GS:
        if pressed:
            if shift:
                eyesy.toggle_midi_notes_mute()
            else:
                eyesy.toggle_midi_clock_mute()
        return

    # shift + D# cycles the knob sequencer, the plain key still toggles persist
    if k == KEY_DS and pressed and shift:
        eyesy.knob_seq_record_key()
        return

    button = EYESY_BUTTON.get(k)
    if button is not None:
        eyesy.dispatch_key_event(button, v)
