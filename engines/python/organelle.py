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
# knob above them, left to right. The white keys are the colours: C and D step
# the foreground palette, E and F the background, and either pair pressed
# together switches that palette's wobble. G is the MIDI channel. A and B are
# spare.
#
# Everything up here acts on the way up rather than the way down. It has to:
# on the way down there is no telling a single key from the first half of a
# chord. The black keys already worked this way - they double as their knob's
# depth modifier - so the whole octave now reads as one rule, and the lower
# octave keeps acting the moment it is pressed.
UPPER_OCTAVE_FIRST = 13

UPPER_C, UPPER_D, UPPER_E = 13, 15, 17
UPPER_F, UPPER_G         = 18, 20
UPPER_A, UPPER_B         = 22, 24    # spare

# raw key index -> knob 0-4, the five black keys of the upper octave
KNOB_MOD_KEYS = {14: 0, 16: 1, 19: 2, 21: 3, 23: 4}

# The two palette pairs, in eyesy.PALETTE_FG / PALETTE_BG order. Within a pair
# the first key steps down and the second steps up, and a key only ever looks
# at its own partner - C and F are not a chord.
PALETTE_PAIRS = (
    (UPPER_C, UPPER_D),
    (UPPER_E, UPPER_F),
)

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
    """(palette, side) for a palette key, or None.

    palette is 0 for the foreground pair and 1 for the background, side is 0
    for the key that steps down and 1 for the one that steps up.
    """
    for palette, pair in enumerate(PALETTE_PAIRS):
        if k in pair:
            return palette, pair.index(k)
    return None


def _palette_key(eyesy, palette, side, pressed):
    """One of the four palette keys, going down or coming up.

    A tap steps its palette when it is let go, a hold steps it over and over,
    and the two of a pair pressed together switch that palette's wobble instead
    and mark each other so neither steps on the way up - the same "used as a
    modifier, so its release does nothing" bookkeeping the black keys up here
    use.

    The chord is only read while neither key has begun repeating. Once one has,
    pressing the other is somebody scrolling who wants to go back the other
    way, and reading it as a chord would put them on the wobble switch instead.
    """
    i = (palette * 2) + side
    partner = (palette * 2) + (1 - side)

    if pressed:
        eyesy.palette_key_held[i] = True
        eyesy.palette_key_used[i] = False
        eyesy.palette_key_td[i] = 0
        if eyesy.palette_key_held[partner] \
                and eyesy.palette_key_td[partner] < eyesy.PALETTE_REPEAT_DELAY:
            eyesy.palette_key_used[i] = True
            eyesy.palette_key_used[partner] = True
            # marked either way, so a chord started outside a menu and let go
            # inside one does not leave a key stepping later
            if not eyesy.menu_mode:
                on = eyesy.toggle_palette_mod(palette)
                oled.notify(eyesy.PALETTE_NAMES[palette],
                            eyesy.cycle_text() if on else "steady")
        return

    eyesy.palette_key_held[i] = False
    if not eyesy.palette_key_used[i] and not eyesy.menu_mode:
        # no notification: stepping is visible in the picture and on the
        # status page, and 43 palettes tapped through would be 43 messages
        eyesy.step_palette(palette, side)
    eyesy.palette_key_used[i] = False


def dispatch_key(eyesy, k, v):
    """Called from osc.py for every raw organelle key event."""
    pressed = v > 0
    shift = eyesy.key2_status

    # The upper octave white keys are the colours. A pair together switches
    # that palette's wobble, which unlike the knob wobble runs on the Auto
    # Random Cycle clock rather than the trigger - a palette that changed on
    # every kick drum would be a strobe.
    found = palette_for_key(k)
    if found is not None:
        _palette_key(eyesy, found[0], found[1], pressed)
        return

    # Upper G steps the MIDI channel, one per press. It works in a menu too:
    # it is a setting, and the MIDI page is where you would be looking while
    # you set it.
    if k == UPPER_G:
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
