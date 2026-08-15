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

# Upper octave. The white keys recall modes and the black keys switch random
# modulation on and off for the knob above them, left to right.
UPPER_OCTAVE_FIRST = 13
NUM_MODE_SLOTS = 7

# raw key index -> mode slot, the seven white keys of the upper octave
MODE_SLOTS = {13: 0, 15: 1, 17: 2, 18: 3, 20: 4, 22: 5, 24: 6}
SLOT_NAMES = ["C", "D", "E", "F", "G", "A", "B"]

# raw key index -> knob 0-4, the five black keys of the upper octave
KNOB_MOD_KEYS = {14: 0, 16: 1, 19: 2, 21: 3, 23: 4}

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
}


def is_organelle():
    return os.environ.get("EYESY_PLATFORM", "") == "organelle_s"


def slot_for_key(k):
    """Mode slot 0-6 for an upper octave white key, or None."""
    return MODE_SLOTS.get(k)


def knob_for_key(k):
    """Knob 0-4 for an upper octave black key, or None."""
    return KNOB_MOD_KEYS.get(k)


def _recall_mode(eyesy, slot):
    name = eyesy.key_modes[slot]
    if not name:
        oled.notify(SLOT_NAMES[slot], "not assigned")
        return
    try:
        eyesy.set_mode_by_name(name)
    except ValueError:
        print(f"key slot {slot} points at missing mode {name}")
        oled.notify(SLOT_NAMES[slot], f"missing: {name}")
        return
    oled.notify(SLOT_NAMES[slot], name)


def _assign_mode(eyesy, slot):
    eyesy.key_modes[slot] = eyesy.mode
    eyesy.config["key_modes"] = list(eyesy.key_modes)
    eyesy.save_config_file()
    oled.send_keymap(slot, eyesy.mode)
    oled.notify(f"{SLOT_NAMES[slot]} set", eyesy.mode)
    print(f"assigned mode {eyesy.mode} to key slot {slot}")


def dispatch_key(eyesy, k, v):
    """Called from osc.py for every raw organelle key event."""
    pressed = v > 0
    shift = eyesy.key2_status

    # the white keys of the upper octave recall modes, holding shift while
    # pressing one stores the mode that is playing right now
    slot = slot_for_key(k)
    if slot is not None:
        if pressed and not eyesy.menu_mode:
            if shift:
                _assign_mode(eyesy, slot)
            else:
                _recall_mode(eyesy, slot)
        return

    # The black keys up there wobble the knob above them. The key doubles as
    # that knob's depth modifier, so it acts on release and only when it was
    # tapped rather than held while the knob was turned.
    knob = knob_for_key(k)
    if knob is not None:
        if pressed:
            eyesy.knob_mod_key_held[knob] = True
            eyesy.knob_mod_key_used[knob] = False
        else:
            eyesy.knob_mod_key_held[knob] = False
            if not eyesy.knob_mod_key_used[knob]:
                # A playing sequence is writing these knobs itself, so adding
                # a wobble would be two things driving one control. Switching
                # an existing one off stays allowed.
                if not eyesy.knob_mod[knob] and eyesy.knob_seq_state == "playing":
                    oled.notify("Modulation", "knob seq is playing")
                else:
                    on = eyesy.toggle_knob_mod(knob)
                    oled.notify(f"Knob {knob + 1}",
                                "modulating" if on else "steady")
            eyesy.knob_mod_key_used[knob] = False
        return

    # The pedal saves a scene. It deliberately does not go through the save
    # key's own handler: that one deletes the current scene when it is held for
    # a second, which is a foot resting on a pedal.
    if k == FOOTSWITCH:
        if pressed and not eyesy.menu_mode:
            eyesy.save_scene()
            name = eyesy.scenes[-1]["name"] if eyesy.scenes else ""
            oled.notify("Scene saved", name)
        return

    # A# steps the auto picker: off, random modes, random scenes, off again
    if k == KEY_AS:
        if pressed and not eyesy.menu_mode:
            state = eyesy.cycle_auto_random()
            if state == eyesy.AUTO_RANDOM_SCENES and not eyesy.scenes:
                oled.notify("Auto Random", "no scenes to pick")
            else:
                oled.notify("Auto Random", eyesy.auto_random_text())
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
