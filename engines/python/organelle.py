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

# Upper octave. The black keys switch random modulation on and off for the
# knob above them, left to right. Three of the white keys took over what used
# to be Mode Keys: C and D wobble a palette, E steps the MIDI channel. F, G, A
# and B are unassigned.
UPPER_OCTAVE_FIRST = 13

UPPER_C = 13    # foreground palette wobble on / off
UPPER_D = 15    # background palette wobble on / off
UPPER_E = 17    # midi channel +1 per press, wrapping at 16

# raw key index -> knob 0-4, the five black keys of the upper octave
KNOB_MOD_KEYS = {14: 0, 16: 1, 19: 2, 21: 3, 23: 4}

# raw key index -> which palette, see eyesy.PALETTE_FG / PALETTE_BG
PALETTE_MOD_KEYS = {UPPER_C: 0, UPPER_D: 1}

# the panel button the pedal borrows when it is set to Trigger
EYESY_TRIGGER_BUTTON = 10

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


def knob_for_key(k):
    """Knob 0-4 for an upper octave black key, or None."""
    return KNOB_MOD_KEYS.get(k)


def palette_for_key(k):
    """Palette 0 or 1 for upper C or D, or None."""
    return PALETTE_MOD_KEYS.get(k)


def dispatch_key(eyesy, k, v):
    """Called from osc.py for every raw organelle key event."""
    pressed = v > 0
    shift = eyesy.key2_status

    # Upper C and D wobble a palette. Unlike the knob wobble this runs on the
    # Auto Random Cycle clock rather than the trigger - a palette that changed
    # on every kick drum would be a strobe.
    palette = palette_for_key(k)
    if palette is not None:
        if pressed and not eyesy.menu_mode:
            on = eyesy.toggle_palette_mod(palette)
            oled.notify(eyesy.PALETTE_NAMES[palette],
                        eyesy.cycle_text() if on else "steady")
        return

    # Upper E steps the MIDI channel, one per press. It works in a menu too:
    # it is a setting, and the MIDI page is where you would be looking while
    # you set it.
    if k == UPPER_E:
        eyesy.midi_channel_key(pressed)
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
            # the held and used bookkeeping runs either way, so a key pressed
            # outside a menu and let go inside one does not get stuck
            if not eyesy.knob_mod_key_used[knob] and not eyesy.menu_mode:
                # A playing sequence is writing these knobs itself, so adding
                # a wobble would be two things driving one control. Switching
                # an existing one off stays allowed.
                if not eyesy.knob_mod[knob] and eyesy.knob_seq_state == "playing":
                    oled.warn("Modulation", "knob seq is playing")
                else:
                    on = eyesy.toggle_knob_mod(knob)
                    oled.notify(f"Knob {knob + 1}",
                                "modulating" if on else "steady")
            eyesy.knob_mod_key_used[knob] = False
        return

    # The pedal does one of two things, picked in Settings > System.
    if k == FOOTSWITCH:
        eyesy.footswitch_status = pressed

        if pressed:
            trigger = eyesy.config["footswitch"] == eyesy.FOOTSWITCH_TRIGGER

            # Shift arms the knob sequencer, and disarms it next time. This
            # does not go through the trigger key the way the plain press
            # does: holding key 10 down is what starts the test tone and the
            # repeating trigger, and neither belongs on a pedal that is being
            # used to arm a recorder.
            if trigger and shift and not eyesy.menu_mode:
                eyesy.knob_seq_record_key()
                eyesy.footswitch_trigger_held = False
                return

            # Unshifted it is the panel's trigger key, so it goes through that
            # key's own handler and picks up what the key does rather than a
            # copy of some of it: the trigger and the test tone while held.
            #
            # Which of the two it is gets latched on the way down. Changing
            # the setting with the pedal held would otherwise send the release
            # to the other branch, and key10_status would stay on with the
            # analysis input stuck at a sine wave until the key was pressed.
            eyesy.footswitch_trigger_held = trigger and not shift

        if eyesy.footswitch_trigger_held:
            eyesy.dispatch_key_event(EYESY_TRIGGER_BUTTON, v)
            if not pressed:
                eyesy.footswitch_trigger_held = False
            return

        # Saving deliberately does not go through the save key's own handler:
        # that one deletes the current scene when it is held for a second,
        # which is also what a foot resting on a pedal looks like.
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
                oled.warn("Auto Random", "no scenes to pick")
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
