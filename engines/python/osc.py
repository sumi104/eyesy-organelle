import sys
import liblo
import os

import oled
import organelle
import streamer

eyesy = None
osc_server = None
osc_target = None
organelle_keys = False

# OSC callbacks
def fallback(path, args):
    pass

def get_mode_name_from_path(path):
    parts = os.path.normpath(path).split(os.sep)
    
    # Ensure the path has at least two parts and ends with "main.py"
    if len(parts) < 2 or parts[-1] != "main.py":
        return None

    return parts[-2]

def set_callback(path, args):
    global eyesy
    name = get_mode_name_from_path(args[0])
    print(f"attempting to load: {args[0]}")
    try :
        eyesy.set_mode_by_name(name)
        print("set mode to: " + str(eyesy.mode) + " with index " + str(eyesy.mode_index) + " reloading...")
        eyesy.reload_mode()
    except:
        print(f"couldn't set mode {args[0]}, check USB or SD")
 
def new_callback(path, args):
    global eyesy
    name = args[0]
    eyesy.load_new_mode(name)
   
def reload_callback(path, args):
    global eyesy
    print("reloading: " + str(eyesy.mode))
    eyesy.reload_mode()
 
def screengrab_callback(path, args):
    global eyesy
    print("screen grab message")
    eyesy.screengrab_flag = True

def knobs_callback(path, args):
    global eyesy
    #print ("received message: " + str(args[0]))
    for i,v in enumerate(eyesy.knob_last):
        if args[i] != eyesy.knob_last[i]:
            eyesy.knob_last[i] = args[i]
            eyesy.knob_hardware[i] = float(args[i] / 1023)
            #print(f"knob {i} {eyesy.knob_hardware[i]}")

def keys_callback(path, args) :
    global eyesy
    k, v = args
    if organelle_keys :
        organelle.dispatch_key(eyesy, k, v)
    else :
        eyesy.dispatch_key_event(k,v)

def encoder_turn_callback(path, args) :
    global eyesy
    # the hardware process already paged the oled, this is here for menus
    eyesy.encoder_turn = 1 if args[0] == 1 else -1

def encoder_button_callback(path, args) :
    global eyesy
    eyesy.encoder_button = args[0] > 0
    if args[0] > 0 : eyesy.encoder_press = True

# the encoder was pressed on an oled page that owns an on/off setting,
# the display picks the new state up from the next state message
def oled_toggle_callback(path, args) :
    global eyesy
    action = args[0]
    if action == "stream" :
        on = streamer.toggle(eyesy)
        oled.notify("Live On" if on else "Live Off")
    elif action == "clock" :
        eyesy.toggle_midi_clock_mute()
    else :
        print(f"unknown oled toggle {action}")

def init (eyesy_object) :
    global osc_server, osc_target, eyesy, organelle_keys
    eyesy = eyesy_object
    organelle_keys = organelle.is_organelle()

    # OSC init server and client
    try:
        osc_target = liblo.Address(4001)
    except liblo.AddressError as err:
        print(err)

    try:
        osc_server = liblo.Server(4000)
    except liblo.ServerError as err:
        print(str(err))
    osc_server.add_method("/knobs", 'iiiiii', knobs_callback)
    osc_server.add_method("/key", 'ii', keys_callback)
    osc_server.add_method("/encoder/turn", 'i', encoder_turn_callback)
    osc_server.add_method("/encoder/button", 'i', encoder_button_callback)
    osc_server.add_method("/oled/toggle", 's', oled_toggle_callback)
    osc_server.add_method("/reload", 'i', reload_callback)
    osc_server.add_method("/screengrab", 'i', screengrab_callback)
    osc_server.add_method("/set", 's', set_callback)
    osc_server.add_method("/new", 's', new_callback)
    osc_server.add_method(None, None, fallback)

def recv() :
    global osc_server
    while (osc_server.recv(1)):
        pass

def send(addr, *args) :
    global osc_target
    try :
        liblo.send(osc_target, addr, *args)
    except Exception as e :
        print(f"osc send to {addr} failed: {e}")

def close():
    global osc_server
    if osc_server:
        osc_server.free()  # Free the resources used by the OSC server
        osc_server = None
        print("OSC server closed successfully.")

