import time
import traceback
import mido

input_port = None
input_port_usb = None
midi_clock_count = 0

# --- incoming clock tempo ------------------------------------------------
#
# MIDI clock is 24 ticks to the quarter note, so the time across 24 of them
# is one beat and 60 over it is the tempo. Measuring a whole beat rather than
# one tick is what makes this readable: per tick jitter averages out over the
# 24, and a clock arriving down a DIN cable has plenty of it.

CLOCK_TICKS_PER_BEAT = 24

# how long the last beat's worth of ticks may be before the tempo is stale.
# A stopped sequencer sends nothing at all -- there is no stop message being
# read here -- so silence is the only sign, and two seconds is slower than
# any tempo anyone will use.
CLOCK_SILENCE = 2.0

# smoothing, or the last digit flickers at twenty updates a second
CLOCK_SMOOTHING = 0.25

_tick_times = []
_clock_bpm = 0.0
_clock_last = 0.0

# The program change most recently accepted, as the number the settings screen
# would call it: that screen lists pgm 1 to 128 while the wire carries 0 to
# 127, and a sender that disagrees about which end to count from is the whole
# reason for showing this.
last_program = 0
last_program_at = 0.0


def _note_clock_tick(now):
    global _clock_bpm, _clock_last

    _clock_last = now
    _tick_times.append(now)
    if len(_tick_times) <= CLOCK_TICKS_PER_BEAT:
        return
    del _tick_times[:-(CLOCK_TICKS_PER_BEAT + 1)]

    beat = now - _tick_times[0]
    if beat <= 0:
        return
    bpm = 60.0 / beat
    if not (20.0 <= bpm <= 400.0):
        # a gap in the stream rather than a tempo anyone is playing
        return
    _clock_bpm = bpm if _clock_bpm == 0.0 else \
        _clock_bpm + (bpm - _clock_bpm) * CLOCK_SMOOTHING


def clock_bpm():
    """Tempo of the incoming MIDI clock, or 0.0 when none is arriving."""
    if _clock_bpm == 0.0 or time.monotonic() - _clock_last > CLOCK_SILENCE:
        return 0.0
    return _clock_bpm


def clock_reset():
    """Forget the tempo, for tests and for a source change."""
    global _clock_bpm, _clock_last
    del _tick_times[:]
    _clock_bpm = 0.0
    _clock_last = 0.0

def _handle_note(eyesy, message):
    #print(f"Note message: {message}")
    if eyesy.midi_notes_muted:
        return
    if (message.channel + 1) == eyesy.config["midi_channel"]:
        num = message.note 
        val = message.velocity
        if val > 0 and message.type == "note_on":
            eyesy.midi_notes[num] = 1
            # 1 is trigger source for note, 2 for notes or audio
            if eyesy.config["trigger_source"] == 1 or eyesy.config["trigger_source"] == 2: eyesy.trig = True 
            # select mode from note 
            if eyesy.config["notes_change_mode"] == 1:
                eyesy.mode_index = num % len(eyesy.mode_names)
                eyesy.set_mode_by_index(eyesy.mode_index)
        else :
            eyesy.midi_notes[num] = 0

def _handle_control_change(eyesy, message):
    #print(f"Control Change message: {message}")
    if (message.channel + 1) == eyesy.config["midi_channel"]:
        num = message.control
        val = message.value
        if not eyesy.menu_mode : # don't update knobs in menu mode (interferes with test)
            if message.control == eyesy.config["knob1_cc"] : eyesy.knob_hardware[0] = val / 127.
            if message.control == eyesy.config["knob2_cc"] : eyesy.knob_hardware[1] = val / 127.
            if message.control == eyesy.config["knob3_cc"] : eyesy.knob_hardware[2] = val / 127.
            if message.control == eyesy.config["knob4_cc"] : eyesy.knob_hardware[3] = val / 127.
            if message.control == eyesy.config["knob5_cc"] : eyesy.knob_hardware[4] = val / 127.
        if message.control == eyesy.config["auto_clear_cc"] : 
            if val > 64 :
                eyesy.auto_clear = True
            else:
                eyesy.auto_clear = False
        if message.control == eyesy.config["fg_palette_cc"] : 
            eyesy.fg_palette = val % len(eyesy.palettes)
        if message.control == eyesy.config["bg_palette_cc"] : 
            eyesy.bg_palette = val % len(eyesy.palettes)
        if message.control == eyesy.config["mode_cc"] : 
            eyesy.mode_index = val % len(eyesy.mode_names)
            eyesy.set_mode_by_index(eyesy.mode_index)
       
def _handle_program_change(eyesy, message):
    #print(f"Program Change message: {message}")
    global last_program, last_program_at
    if (message.channel + 1) == eyesy.config["midi_channel"]:
        # Remembered before the mapping is looked up, and remembered even when
        # there is no mapping: "the number arrived, nothing is assigned to it"
        # is the answer you are after when a program change did nothing, and
        # it is the case where the row would otherwise be empty.
        last_program = message.program + 1
        last_program_at = time.monotonic()
        if f"pgm_{message.program + 1}" in eyesy.config["pc_map"]:
            scene = eyesy.config["pc_map"][f"pgm_{message.program + 1}"]
            print(f"attempting to load scene {scene}")
            eyesy.recall_scene_by_name(scene)

def _handle_clock(eyesy, message):
    global midi_clock_count

    # Measured whether or not the clock is muted. Muting stops the visuals
    # following it, it does not stop it arriving, and the MIDI page should say
    # what is out there either way -- which is what the Link readout does.
    _note_clock_tick(time.monotonic())

    if eyesy.midi_clock_muted:
        return
    ts = eyesy.config["trigger_source"]
    # 3,4,5,6 of trigger source are midi clock selections
    if ts > 2:
        if ts == 3:
            if (midi_clock_count % 6) == 0: eyesy.trig = True
        elif ts == 4:
            if (midi_clock_count % 12) == 0: eyesy.trig = True
        elif ts == 5:
            if (midi_clock_count % 24) == 0: eyesy.trig = True
        elif ts == 6:
            if (midi_clock_count % 96) == 0: eyesy.trig = True
    midi_clock_count += 1

def init():
    global input_port, input_port_usb

    # first ttymidi
    try:
        input_port = mido.open_input('ttymidi:MIDI in 128:0') 
    except Exception as e:
        print(f"Error initializing ttymidi input port: {e}")
        input_port = None

    # try to get a USB midi port
    input_ports = mido.get_input_names()
    print(input_ports)
    valid_port = next((port for port in input_ports if not port.startswith(("Midi Through", "ttymidi", "System"))), None)
    if valid_port != None:
        try:
            print(f"trying to open: {valid_port}")
            input_port_usb = mido.open_input(valid_port) 
        except Exception as e:
            print(f"Error initializing midi input port: {e}")
            input_port_usb = None
    else :
        print(f"USB MIDI not found")
    
def close():
    global input_port, input_port_usb

    for port, name in [(input_port, "ttymidi"), (input_port_usb, "USB MIDI")]:
        if port:
            try:
                print(f"Closing {name} input port.")
                port.close()
            except Exception as e:
                print(f"Error closing {name} input port: {e}")

def recv(eyesy, input_port):
    if not input_port:
        #print("Input port is not initialized.")
        return

    try:
        messages = []
        for message in input_port.iter_pending():  # Non-blocking iteration
            messages.append(message)

        for message in messages:
            try:
                if message.type == 'clock':
                    _handle_clock(eyesy, message)
                if message.type == 'note_on' or message.type == 'note_off':
                    _handle_note(eyesy, message)
                elif message.type == 'control_change':
                    _handle_control_change(eyesy, message)
                elif message.type == 'program_change':
                    _handle_program_change(eyesy, message)
            except Exception as e:
                print(traceback.format_exc())
                print(f"Error processing message {message}: {e}")
    except Exception as e:
        print(f"Error receiving messages: {e}")

def recv_ttymidi(eyesy):
    global input_port
    recv(eyesy, input_port)

def recv_usbmidi(eyesy):
    global input_port_usb
    recv(eyesy, input_port_usb)
