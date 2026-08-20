import fileinput
import random
import math
import pygame
import traceback
import imp
import os
import glob
import sys
import time
import json
import helpers
import file_operations
import csv
import color_palettes
import config
import oled
import audio_thru

class Eyesy:

    def __init__(self):
        self.VERSION = "3.1"
        # config stuff 
        self.GRABS_PATH = "/sdcard/Grabs/"
        self.MODES_PATH = "/sdcard/Modes/"
        self.SCENES_PATH = "/sdcard/Scenes/"
        self.SYSTEM_PATH = "/sdcard/System/"
       
        self.COMPVIDS = ["NTSC","NTSC-J","NTSC-443","PAL","PAL-M","PAL-N","PAL60","SECAM"]

        self.RESOLUTIONS = [
            { "name" : "640 x 480",
              "res"  : (640,480)
            },
            { "name" : "720 x 480",
              "res"  : (720,480)
            },
            { "name" : "800 x 600",
              "res"  : (800,600)
            },
            { "name" : "1280 x 720",
              "res"  : (1280,720)
            },
            { "name" : "1920 x 1080 - slow",
              "res"  : (1920,1080)
            }
        ]
        
        self.RES =  (0,0)
        
        # 3 to 6 are midi clock divisions, 7 to 10 the same divisions from an
        # Ableton Link session. link.DIVISIONS has to agree about the indices
        self.TRIGGER_SOURCES = ["Audio", "MIDI Note", "Audio or MIDI Note", "MIDI Clock 16th Note", "MIDI Clock 8th Note", "MIDI Clock 1/4 Note", "MIDI Clock Whole Note", "Link 16th Note", "Link 8th Note", "Link 1/4 Note", "Link Whole Note"]

        # auto random, cycled by the organelle's A# key
        self.AUTO_RANDOM_OFF, self.AUTO_RANDOM_MODES, self.AUTO_RANDOM_SCENES = 0, 1, 2
        # seconds between picks, -1 draws a fresh interval every time
        self.AUTO_RANDOM_INTERVALS = [15, 30, 50, 60, -1]

        # What the pedal jack does, picked in Settings > System. The index is
        # what "footswitch" holds in the config, so only append to this.
        self.FOOTSWITCH_ACTIONS = ["Save Scene", "Trigger"]
        self.FOOTSWITCH_SAVE = 0
        self.FOOTSWITCH_TRIGGER = 1
        self.AUTO_RANDOM_MIN, self.AUTO_RANDOM_MAX = 15, 60

        # which palette a wobble is aimed at, the index into palette_mod
        self.PALETTE_FG, self.PALETTE_BG = 0, 1
        self.PALETTE_NAMES = ["FG Palette", "BG Palette"]

        self.DEFAULT_CONFIG = {
            "video_resolution": 3,
            "audio_gain": .25,
            "trigger_source":0,
            "fg_palette": 0,
            "bg_palette": 0,
            "midi_channel": 1,
            "knob1_cc": 20,
            "knob2_cc": 21,
            "knob3_cc": 22,
            "knob4_cc": 23,
            "knob5_cc": 24,
            "auto_clear_cc": 25,
            "fg_palette_cc": -1,
            "bg_palette_cc": -1,
            "mode_cc": -1,
            "notes_change_mode": False,
            "pc_map": {},
            # depth is how far the offset can swing either side of the knob,
            # rate is how quickly it gets to each new target. 0.15 comes out
            # at about one turn a second, which reads as a wobble rather than
            # a drift
            "knob_mod_depth": .25,
            "knob_mod_rate": .15,
            # step the wobble on the trigger rather than on a clock of its own,
            # so it follows the audio, the MIDI clock or the Link session
            "knob_mod_sync": True,
            # Seconds between automatic picks, -1 for a random interval. Every
            # part of the instrument that changes on its own runs on this: the
            # A# mode and scene picker, and the palette wobble on upper C and
            # D. One dial for how restless the thing is.
            "auto_random_interval": 30,
            # what the pedal jack does, see FOOTSWITCH_ACTIONS below
            "footswitch": 0,
            # organelle s: how loud the line input is passed straight through
            # to the line output, inside the codec. 0 is muted, which is also
            # what off means here - there is no separate switch. Shift and the
            # volume knob set it. See audio_thru.py
            "audio_thru_volume": 0.0,
            # live video stream to a browser on the network
            "stream_enabled": False,
            "stream_width": 640,
            "stream_fps": 15,
            "stream_smooth": False
        }
        
        self.config = {}

        # some colors we use
        self.BLACK = (0, 0, 0)
        self.WHITE = (255, 255, 255)
        self.LGRAY = (200, 200, 200)
        self.RED = (255, 0, 0)
        self.GREEN = (0, 255, 0)
        self.BLUE = (0, 0, 255)
        self.OSDBG = (0,0,255)

        # screen grabs
        self.lastgrab = None
        self.lastgrab_thumb = None
        self.tengrabs_thumbs = []
        self.grabcount = 0
        self.grabindex = 0
        self.screengrab_flag = False

        # modes
        self.mode_names = []  # list of mode names pupulated from Modes folder on USB drive
        self.mode_index = 0   # index of current mode
        self.mode = ''        # name of current mode
        self.mode_root = ''   # root path of current mode
        self.error = ''       # errors that happend during setup() or run()
        self.run_setup = False # flag to signal main loop to run setup() usually if a mode was reloaded

        # scenes
        self.scenes = []     # 
        self.scene_index = -1  # init to -1 to indicate no scene
        self.save_key_status = False
        self.save_key_time = 0  # for timing how long save key held 
        self.next_numbered_scene = 1
        
        # audio
        self.audio_in = [0] * 100
        self.audio_in_r = [0] * 100
        self.audio_peak = 0
        self.audio_peak_r = 0
        self.audio_scale = 1.0

        # knobs a used by mode 
        self.knob1 = 0
        self.knob2 = 1
        self.knob3 = 1
        self.knob4 = 1
        self.knob5 = 1
       
        # knob values used internally
        self.knob = [.2] * 5
        self.knob_hardware = [.2] * 5
        self.knob_hardware_last = [-1] * 5  # used to filter repetitive knob values so they don't interfere with knob sequencer
        self.knob_snapshot = [.2] * 5
        self.knob_override = [False] * 5
        self.knob_last = [-1] * 5      # used to filter repetitive knob osc messages, but we always want to first one so set to -1

        # what the knobs would read with no modulation on top, which is what
        # a scene stores. same as knob1-5 until a knob is being wobbled
        self.knob_base = [.2] * 5

        # random modulation, one per knob, toggled from the organelle's upper
        # octave black keys. the offset wanders around the knob's position
        # rather than sweeping the whole range
        self.knob_mod = [False] * 5
        self.knob_mod_value = [0.0] * 5
        self.knob_mod_target = [0.0] * 5

        # while a knob is modulating it stops setting a value and shapes the
        # wobble instead: turning it sets the rate, turning it with shift held
        # sets the depth. per knob, seeded from the config
        self.knob_mod_rate = [.15] * 5
        self.knob_mod_depth = [.25] * 5
        self.knob_mod_editing = [None] * 5   # "rate", "depth" or None
        self.knob_mod_capture = [0.0] * 5
        self.knob_mod_unlocked = [False] * 5

        # the upper octave black key that owns each knob's modulation is also
        # its depth modifier, so it only toggles if it was tapped rather than
        # held while its knob was turned
        self.knob_mod_key_held = [False] * 5
        self.knob_mod_key_used = [False] * 5

        # midi stuff 
        self.midi_notes = [0] * 128
        self.midi_notes_last = [0] * 128
        self.midi_note_new = False
        self.midi_clk = 0
        self.new_midi = False
        self.usb_midi_name = ''
        self.usb_midi_present = False

        # system stuff 
        self.led = 0
        self.new_led = False
        self.screen = None  # ref to main surface, for doing screenshots
        self.xres = 1280
        self.yres = 720
        self.bg_color = (0, 0, 0)
        self.memory_used = 0
        self.ip = ''
        self.auto_clear = True
        self.restart = False
        self.show_osd = False
        self.menu_mode = False
        self.osd_first = False # when osd is first turned on this is used to gather info
        self.trig = False
        self.fps = 0
        self.frame_count = 0
        self.font = None
        self.running_from_usb = False
        self.usb_midi_device = None

        # performance mutes, these live on the organelle black keys
        self.audio_muted = False
        self.midi_clock_muted = False
        self.midi_notes_muted = False
        self.freeze = False

        # organelle encoder, the hardware process pages the oled itself and
        # sends these along in case a menu wants them
        self.encoder_turn = 0     # -1, 0 or 1, cleared every frame
        self.encoder_press = False
        self.encoder_button = False

        # off, then random modes, then random scenes, back to off
        self.auto_random = 0
        self.auto_random_next = 0.0

        # menu stuff
        self.current_screen = None
        self.menu_screens = {}

        # key stuff
        self.key1_press = False
        self.key2_press = False
        self.key3_press = False
        self.key4_press = False
        self.key5_press = False
        self.key6_press = False
        self.key7_press = False
        self.key8_press = False
        self.key9_press = False
        self.key10_press = False
        
        self.key2_status = False  # shift key pressed or not
        self.key4_status = False  
        self.key5_status = False  
        self.key6_status = False  
        self.key7_status = False  
        self.key10_status = False  
        # true from the moment the pedal goes down until it comes back up, if
        # it was set to Trigger when it went down. See organelle.dispatch_key.
        self.footswitch_trigger_held = False
        # true whenever the pedal is down, whatever it is set to
        self.footswitch_status = False

        # counters for key repeaters
        self.key4_td = 0
        self.key5_td = 0
        self.key6_td = 0
        self.key7_td = 0
        self.key10_td = 0

        # color stuff
        self.palettes = color_palettes.abcd_palettes
        self.fg_palette = 0
        self.bg_palette = 0
        self.color_lfo_inc = 0
        self.color_lfo_index = 0
        self.palettes_user_defined = False

        # Random palette changes, switched on from the upper octave C and D
        # keys. Two independent clocks rather than one: started at different
        # moments the two palettes should change at different moments, and
        # tying them together would only make the picture blink.
        self.palette_mod = [False, False]
        self.palette_mod_next = [0.0, 0.0]

        # knob sequencer stuff
        self.knob_seq = []
        self.knob_seq_last_values = [-1] * 5
        self.knob_seq_index = 0
        self.knob_seq_state = "stopped"

        # gain control shortcut
        self.gain_knob_unlocked = False
        self.gain_knob_capture = 0
        self.gain_value_snapshot = 0

        # the same shortcut on the volume knob, for the analogue passthrough.
        # knob 5 is the one the panel prints "Volume" on, and shift is the
        # only time it is not busy being a mode parameter
        self.thru_knob_unlocked = False
        self.thru_knob_capture = 0
        self.thru_knob_last = -1
        self.thru_value_snapshot = 0

    
        self.clear_flags()

    def ensure_directories(self):
        paths = [self.GRABS_PATH, self.MODES_PATH, self.SCENES_PATH, self.SYSTEM_PATH]
        for path in paths:
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
                print(f"Created directory: {path}")
            else:
                print(f"Exists: {path}")

    def load_palettes(self):
        grads = os.path.join(self.SYSTEM_PATH, "palettes.json")
        if not os.path.exists(grads):
            print(f"File not found: {grads}, using default palettes.")
            self.palettes = color_palettes.abcd_palettes
            return 

        try:
            with open(grads, "r") as file:
                data = json.load(file)

            if (isinstance(data, list) and len(data) > 0 and all(
                isinstance(entry, dict) and
                "name" in entry and isinstance(entry["name"], str) and
                all(k in entry and isinstance(entry[k], list) and len(entry[k]) == 3 and 
                    all(isinstance(v, (int, float)) for v in entry[k])
                    for k in ["a", "b", "c", "d"])
                for entry in data
            )):
                print(f"Loaded palettes from {grads}")
                print(data)
                self.palettes = data
                self.palettes_user_defined = True
                return 
            else:
                print(f"Invalid structure or empty list in {grads}, using default palettes.")

        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading {grads}: {e}, using default palettes.")

        self.palettes = color_palettes.abcd_palettes




    def load_config_file(self) :
        config_file = self.SYSTEM_PATH + "config.json"
        if not(os.path.isdir(self.SYSTEM_PATH)) :
            print('No system folder, creating...')
            os.system('mkdir ' + self.SYSTEM_PATH)

        try:
            # Load configuration, raising errors for file or JSON issues
            self.config = config.load_config(config_file, self.DEFAULT_CONFIG)
        except FileNotFoundError as e:
            print(f"Error loading configuration: {e}")
            print("Using all default values. Saving File.")
            self.config = self.DEFAULT_CONFIG
            config.save_config(config_file, self.config)
        except ValueError as e:
            print(f"Error loading configuration: {e}")
            print("Using all default values.")
            self.config = self.DEFAULT_CONFIG

        self.validate_config()
        print("Current Configuration:", self.config)

        try:
            # set values from configg
            self.RES = self.RESOLUTIONS[self.config["video_resolution"]]["res"]
            self.bg_palette = self.config["bg_palette"]
            self.fg_palette = self.config["fg_palette"]
        except :
            print("Error setting config value")
    
    def _validate_config_int(self, field, minv, maxv) :
        self.config[field] = (
            self.config.get(field)
            if isinstance(self.config.get(field), int) and minv <= self.config[field] <= maxv
            else self.DEFAULT_CONFIG[field]
        )

    def _validate_config_float(self, field, minv, maxv) :
        self.config[field] = (
            self.config.get(field)
            if isinstance(self.config.get(field), float) and minv <= self.config[field] <= maxv
            else self.DEFAULT_CONFIG[field]
        )

    def _validate_config_bool(self, field):
        self.config[field] = (
            self.config.get(field)
            if isinstance(self.config.get(field), bool)
            else self.DEFAULT_CONFIG[field]
        )

    def validate_config(self):
        # Validate each field in self.config, falling back to defaults if needed
        self._validate_config_int("midi_channel", 1, 16)
        self._validate_config_int("video_resolution", 0, len(self.RESOLUTIONS))
        self._validate_config_float("audio_gain", 0, 1)
        self._validate_config_int("fg_palette", 0, len(self.palettes)-1)
        self._validate_config_int("bg_palette", 0, len(self.palettes)-1)
        self._validate_config_int("trigger_source", 0, len(self.TRIGGER_SOURCES)-1)
        self._validate_config_int("knob1_cc", -1, 127)
        self._validate_config_int("knob2_cc", -1, 127)
        self._validate_config_int("knob3_cc", -1, 127)
        self._validate_config_int("knob4_cc", -1, 127)
        self._validate_config_int("knob5_cc", -1, 127)
        self._validate_config_int("auto_clear_cc", -1, 127)
        self._validate_config_int("fg_palette_cc", -1, 127)
        self._validate_config_int("bg_palette_cc", -1, 127)
        self._validate_config_int("mode_cc", -1, 127)
        self._validate_config_int("notes_change_mode", 0, 1)
        self._validate_config_bool("stream_enabled")
        self._validate_config_bool("stream_smooth")
        self._validate_config_bool("knob_mod_sync")
        self._validate_config_int("auto_random_interval", -1, 3600)
        self._validate_config_int("footswitch", 0, len(self.FOOTSWITCH_ACTIONS) - 1)
        self._validate_config_float("audio_thru_volume", 0.0, 1.0)
        self._validate_config_float("knob_mod_depth", 0.0, 1.0)
        self._validate_config_float("knob_mod_rate", 0.005, 1.0)
        # the config holds the starting point, each knob keeps its own after
        # that so they can be shaped independently while performing
        self.knob_mod_rate = [self.config["knob_mod_rate"]] * 5
        self.knob_mod_depth = [self.config["knob_mod_depth"]] * 5
        self._validate_config_int("stream_width", 320, 960)
        self._validate_config_int("stream_fps", 1, 30)
        # Mode Keys is gone - the upper octave white keys wobble the palettes
        # and step the midi channel now. Drop what it left in the config file
        # rather than carrying a dead setting around forever.
        self.config.pop("key_modes", None)

    def save_config_file(self) :
        config_file = self.SYSTEM_PATH + "config.json"
        config.save_config(config_file, self.config)

    def set_osd(self, stat) :
        self.show_osd = stat
        self.osd_first = True
  
    # run the pre and post logic function for a screen when entering / leaving
    def switch_menu_screen(self,s) :
        if self.current_screen is not None: self.current_screen.after()
        self.current_screen = self.menu_screens[s]
        self.current_screen.before()
        #self.screen.fill(self.bg_color) 

    def exit_menu(self):
        #self.screen.fill(self.bg_color) 
        self.menu_mode = False
        self.set_osd(False)

    def toggle_menu(self) :
        if self.menu_mode:
            #self.screen.fill(self.bg_color) 
            self.menu_mode = False
            self.set_osd(False)
        else :
            self.set_osd(False)
            self.menu_mode = True
            self.switch_menu_screen("home")
 
    def toggle_osd(self) :
        # if on osd or menu screen, exit out of both
        if self.show_osd or self.menu_mode:
            #self.screen.fill(self.bg_color) 
            self.menu_mode = False
            self.set_osd(False)
        else :
            #self.screen.fill(self.bg_color) 
            self.set_osd(True)
            self.menu_mode = False

    def toggle_auto_clear(self):
        if not self.auto_clear :
            self.auto_clear = True
        else :
            self.auto_clear = False

    # silences the analysis input so the modes stop reacting, the audio
    # output of the instrument is untouched
    def toggle_audio_mute(self):
        self.audio_muted = not self.audio_muted
        oled.notify("Audio Muted" if self.audio_muted else "Audio On")
        print(f"audio mute {self.audio_muted}")

    # holds the last drawn frame, for cutting the visuals dead mid set
    def toggle_freeze(self):
        self.freeze = not self.freeze
        oled.notify("Freeze" if self.freeze else "Freeze Off")
        print(f"freeze {self.freeze}")

    def toggle_midi_clock_mute(self):
        self.midi_clock_muted = not self.midi_clock_muted
        oled.notify("Clock Muted" if self.midi_clock_muted else "Clock On")
        print(f"midi clock mute {self.midi_clock_muted}")

    def toggle_midi_notes_mute(self):
        self.midi_notes_muted = not self.midi_notes_muted
        if self.midi_notes_muted:
            # note offs are dropped while muted, so let go of anything held
            for i in range(0, 128):
                self.midi_notes[i] = 0
        oled.notify("Notes Muted" if self.midi_notes_muted else "Notes On")
        print(f"midi note mute {self.midi_notes_muted}")

    def set_mode_by_index (self, index) :
        self.mode_index = index
        self.mode = self.mode_names[self.mode_index]
        self.mode_root = self.MODES_PATH + self.mode + "/"
        print("setting mode: " + self.mode_root)
        self.error = ''

    def set_mode_by_name(self, name):
        """Sets the mode by name if it exists in mode_names, otherwise raises an exception."""
        if name not in self.mode_names:
            raise ValueError(f"Mode '{name}' not found in mode_names.")
        
        # Set the mode properties
        self.mode = name
        self.mode_index = self.mode_names.index(name)
        self.mode_root = self.MODES_PATH + self.mode + "/"
        print("setting mode: " + self.mode_root)
        self.error = ''  # Clear any existing errors

    def next_mode (self) :
        self.mode_index += 1
        if self.mode_index >= len(self.mode_names) : 
            self.mode_index = 0
        self.set_mode_by_index(self.mode_index)

    def prev_mode (self) :
        self.mode_index -= 1
        if self.mode_index < 0 : 
            self.mode_index = len(self.mode_names) - 1
        self.set_mode_by_index(self.mode_index)

    def next_bg_palette (self) :
        self.bg_palette += 1
        if self.bg_palette >= len(self.palettes) : 
            self.bg_palette = 0

    def prev_bg_palette (self) :
        self.bg_palette -= 1
        if self.bg_palette < 0 : 
            self.bg_palette = len(self.palettes) - 1

    def next_fg_palette (self) :
        self.fg_palette += 1
        if self.fg_palette >= len(self.palettes) : 
            self.fg_palette = 0

    def prev_fg_palette (self) :
        self.fg_palette -= 1
        if self.fg_palette < 0 : 
            self.fg_palette = len(self.palettes) - 1

    def override_all_knobs(self) :
        for i in range(0,5):
            self.knob_override[i] = True
            self.knob_snapshot[i] = self.knob_hardware[i]
    
    def cc_override_knob(self, i, v) :
        self.knob_override[i] = True
        self.knob_snapshot[i] = self.knob_hardware[i]
        self.knob[i] = v

    # then do this for the modes 
    def update_knobs_and_notes(self) :
        for i in range(0, 5) :
            # a modulating knob is shaping the wobble, not setting a value
            if self.knob_mod[i] :
                self.update_knob_mod_control(i)
                continue

            if self.knob_override[i] :
                if abs(self.knob_snapshot[i] - self.knob_hardware[i]) > .05 :
                    self.knob_override[i] = False
                    self.knob[i] = self.knob_hardware[i]
            else :
                # filter value no change
                if (self.knob_hardware[i] != self.knob_hardware_last[i]) : 
                    self.knob_hardware_last[i] = self.knob_hardware[i]
                    self.knob[i] = self.knob_hardware[i]

        # check for new notes
        for i in range(0, 128):
            if self.midi_notes[i] > 0 and self.midi_notes_last[i] == 0:
                self.midi_note_new = True
    
    # One knob's random modulation, called once a frame while it is on.
    #
    # A trigger picks somewhere new to head for and the offset glides towards
    # it, so what times the movement is whatever is driving the visuals -
    # audio, MIDI notes, MIDI clock or Ableton Link, they all arrive as trig -
    # while the rate knob decides how sharply it gets there. Turned up it
    # lands on the beat, turned down it is still wandering when the next one
    # comes.
    #
    # With nothing triggering, it glides onto its last target and stays there.
    # That is why muting the audio or the clock stops the wobble instead of
    # leaving it running on a clock of its own.
    def update_knob_mod(self, i, stepped) :
        if stepped :
            self.knob_mod_target[i] = random.uniform(-1.0, 1.0)
        elif not self.config["knob_mod_sync"] :
            # free running: pick the next target once this one is reached
            if abs(self.knob_mod_target[i] - self.knob_mod_value[i]) < 0.02 :
                self.knob_mod_target[i] = random.uniform(-1.0, 1.0)

        rate = self.knob_mod_rate[i]
        self.knob_mod_value[i] += \
            (self.knob_mod_target[i] - self.knob_mod_value[i]) * rate

    def toggle_knob_mod(self, i) :
        if not (0 <= i < 5) : return False
        self.knob_mod[i] = not self.knob_mod[i]
        self.knob_mod_value[i] = 0.0
        if self.knob_mod[i] :
            self.knob_mod_target[i] = random.uniform(-1.0, 1.0)

        # Either way the knob changes job, so hold the value it was setting
        # until the knob is next moved. Without this, switching modulation off
        # snaps the value to wherever the knob ended up while it was setting
        # the rate.
        self.knob_override[i] = True
        self.knob_snapshot[i] = self.knob_hardware[i]
        self.knob_mod_editing[i] = None

        print(f"knob {i + 1} modulation {self.knob_mod[i]}")
        return self.knob_mod[i]

    def any_knob_mod(self) :
        return any(self.knob_mod)

    # exponential, so the slow end has usable resolution
    KNOB_MOD_RATE_MIN = .02
    KNOB_MOD_RATE_MAX = .50

    # a modulating knob shapes the wobble instead of setting a value. a plain
    # turn sets the rate, turning it while its own black key is held sets the
    # depth.
    def update_knob_mod_control(self, i) :
        editing = "depth" if self.knob_mod_key_held[i] else "rate"

        # changing what the knob is aimed at, or having just switched
        # modulation on, means picking it up from wherever it physically is
        if self.knob_mod_editing[i] != editing :
            self.knob_mod_editing[i] = editing
            self.knob_mod_capture[i] = self.knob_hardware[i]
            self.knob_mod_unlocked[i] = False
            return

        if not self.knob_mod_unlocked[i] :
            if abs(self.knob_mod_capture[i] - self.knob_hardware[i]) > .05 :
                self.knob_mod_unlocked[i] = True
            else :
                return

        if self.knob_hardware[i] == self.knob_hardware_last[i] : return
        self.knob_hardware_last[i] = self.knob_hardware[i]

        v = self.knob_hardware[i]
        if editing == "depth" :
            self.knob_mod_depth[i] = v
            # the key was used as a modifier, so releasing it must not toggle
            self.knob_mod_key_used[i] = True
            oled.notify_value(f"Depth {i + 1}", v)
        else :
            span = self.KNOB_MOD_RATE_MAX / self.KNOB_MOD_RATE_MIN
            self.knob_mod_rate[i] = self.KNOB_MOD_RATE_MIN * (span ** v)
            oled.notify_value(f"Rate {i + 1}", v)

    def set_knobs(self) :
        # fill these for the modes, but only if shift isn't down
        if not self.key2_status:
            for i in range(0, 5) :
                self.knob_base[i] = self.knob[i]

        # modulation rides on top of the set position, and keeps running with
        # shift held so it does not stall while the gain is being adjusted
        stepped = self.trig and self.config["knob_mod_sync"]
        out = list(self.knob_base)
        for i in range(0, 5) :
            if self.knob_mod[i] :
                self.update_knob_mod(i, stepped)
                out[i] = max(0.0, min(1.0,
                                      out[i] + (self.knob_mod_value[i]
                                                * self.knob_mod_depth[i])))

        if not self.key2_status or self.any_knob_mod() :
            self.knob1 = out[0]
            self.knob2 = out[1]
            self.knob3 = out[2]
            self.knob4 = out[3]
            self.knob5 = out[4]

    # save a screenshot
    def screengrab(self):
       
        # make scenes dir if no exist
        os.makedirs(self.GRABS_PATH, exist_ok=True)

        filenum = 0
        imagepath = self.GRABS_PATH + str(filenum) + ".png"
        while os.path.isfile(imagepath):
            filenum += 1
            imagepath = self.GRABS_PATH + str(filenum) + ".png"
        pygame.image.save( self.screen ,imagepath)
        print("grabbed " + imagepath)

    # load modes,  check if modes are found
    def load_modes(self):
        print("loading modes...")
        got_a_mode = False # at least one mode
        mode_folders = sorted(helpers.get_immediate_subdirectories(self.MODES_PATH), key=lambda s: s.lower() )

        for mode_folder in mode_folders :
            mode_name = str(mode_folder)
            mode_path = self.MODES_PATH+mode_name+'/main.py'
            print(mode_path)
            try :
                imp.load_source(mode_name, mode_path)
                self.mode_names.append(mode_name)
                got_a_mode = True
            except Exception as e:
                print(traceback.format_exc())
        return got_a_mode

    # load a new mode (created from web editor)
    def load_new_mode(self, new_mode) :
        print("not working...")
    
    # reload mode module
    def reload_mode(self) :
        # delete the old, and reload
        if self.mode in sys.modules:  
            del(sys.modules[self.mode]) 
        print("deleted module, reloading")
        try :
            imp.load_source(self.mode, self.mode_root+'/main.py')
            print("reloaded")
        except Exception as e:
            self.error = traceback.format_exc()
            print("error reloading: " + self.error)
        self.run_setup = True # set a flag so setup gets run from main loop
    
    # recent grabs, first check if Grabs folder is available, create if not
    def load_grabs(self):
        if not(os.path.isdir(self.GRABS_PATH)) :
            print('No grab folder, creating...')
            os.system('mkdir ' + self.GRABS_PATH)
        print('loading recent grabs...')
        self.lastgrab = None
        self.lastgrab_thumb = None
        self.tengrabs_thumbs = []
        self.grabcount = 0
        self.grabindex = 0
        for i in range(0,11):
            self.tengrabs_thumbs.append(pygame.Surface((128, 72)))
        
        self.lastgrab = pygame.Surface(self.RES )
        self.lastgrab_thumb = pygame.Surface((128,72) )

        for filepath in sorted(glob.glob(self.GRABS_PATH + '*.jpg')):
            try :
                filename = os.path.basename(filepath)
                print('loading grab: ' + filename)
                img = pygame.image.load(filepath)
                img = img.convert()
                thumb = pygame.transform.scale(img, (128, 72) )
                self.lastgrab = img
                self.lastgrab_thumb = thumb
                self.tengrabs_thumbs[self.grabcount] = thumb
                self.grabcount += 1
            except Exception as e:
                self.error = traceback.format_exc()
                print("error loading grab: " + self.error)
            if self.grabcount > 10: break

    # called from main loop
    def update_scene_save_key(self):
        if self.save_key_status :
            elapsed_time = time.time() - self.save_key_time
            if (elapsed_time > 1) : # held down for 1 seconds, delete the scene
                self.delete_current_scene()
                self.save_key_status = False

    # Auto random. A# steps it through off, random modes, random scenes, and
    # while it is on something new is picked every so often. The picking is
    # the same call the mode and scene keys make, so nothing downstream needs
    # to know this exists.
    def cycle_auto_random(self):
        self.auto_random = (self.auto_random + 1) % 3
        if self.auto_random != self.AUTO_RANDOM_OFF:
            self.arm_auto_random()
            self.pick_random()      # act on the press rather than in a minute
        print(f"auto random {self.auto_random}")
        return self.auto_random

    def cycle_text(self):
        """How often anything on the Auto Random Cycle changes."""
        seconds = self.config["auto_random_interval"]
        return f"every {'random' if seconds < 0 else str(seconds) + 's'}"

    def auto_random_text(self):
        """Short enough for the display to say what it is doing."""
        if self.auto_random == self.AUTO_RANDOM_OFF : return "off"
        what = "modes" if self.auto_random == self.AUTO_RANDOM_MODES else "scenes"
        return f"{what} {self.cycle_text()}"

    def random_interval(self):
        """Seconds until the next automatic change, from Auto Random Cycle.

        Shared by the mode and scene picker and by the palette wobble, so the
        one setting says how restless the instrument is rather than each thing
        having a dial of its own to keep in step.
        """
        interval = self.config["auto_random_interval"]
        if interval < 0:
            interval = random.uniform(self.AUTO_RANDOM_MIN, self.AUTO_RANDOM_MAX)
        return interval

    def arm_auto_random(self):
        self.auto_random_next = time.time() + self.random_interval()

    def pick_random(self):
        """True if it actually moved somewhere."""
        if self.auto_random == self.AUTO_RANDOM_MODES:
            return self.pick_random_mode()
        if self.auto_random == self.AUTO_RANDOM_SCENES:
            return self.pick_random_scene()
        return False

    # never picks what is already playing, or pressing the key looks broken
    def pick_random_mode(self):
        choices = [i for i in range(0, len(self.mode_names)) if i != self.mode_index]
        if not choices : return False
        self.set_mode_by_index(random.choice(choices))
        return True

    def pick_random_scene(self):
        choices = [i for i in range(0, len(self.scenes)) if i != self.scene_index]
        if not choices : return False
        self.recall_scene(random.choice(choices))
        return True

    def update_auto_random(self):
        if self.auto_random == self.AUTO_RANDOM_OFF : return
        if self.menu_mode : return          # not while someone is in a menu
        if time.time() < self.auto_random_next : return
        self.arm_auto_random()
        self.pick_random()

    # ---- palette wobble, upper octave C and D -----------------------------
    #
    # Unlike the knob wobble this does not ride on the trigger. A palette that
    # changed on every kick drum would be a strobe, not a colour scheme, so it
    # runs on the Auto Random Cycle clock instead - the same seconds the mode
    # and scene picker uses. It does not need that picker switched on, though:
    # it only borrows the interval.

    def toggle_palette_mod(self, which):
        if not (0 <= which < 2) : return False
        self.palette_mod[which] = not self.palette_mod[which]
        if self.palette_mod[which]:
            # move now rather than in half a minute, so the key press has
            # something to show for itself. The same reason A# picks on press.
            self.arm_palette_mod(which)
            self.pick_random_palette(which)
        print(f"{self.PALETTE_NAMES[which]} modulation {self.palette_mod[which]}")
        return self.palette_mod[which]

    def arm_palette_mod(self, which):
        self.palette_mod_next[which] = time.time() + self.random_interval()

    def any_palette_mod(self):
        return any(self.palette_mod)

    # never picks the palette already showing, or a cycle goes by with nothing
    # appearing to happen
    def pick_random_palette(self, which):
        current = self.fg_palette if which == self.PALETTE_FG else self.bg_palette
        choices = [i for i in range(0, len(self.palettes)) if i != current]
        if not choices : return False
        pick = random.choice(choices)
        if which == self.PALETTE_FG : self.fg_palette = pick
        else : self.bg_palette = pick
        return True

    def update_palette_mod(self):
        if self.menu_mode : return          # not while someone is in a menu
        now = time.time()
        for which in (self.PALETTE_FG, self.PALETTE_BG):
            if not self.palette_mod[which] : continue
            if now < self.palette_mod_next[which] : continue
            self.arm_palette_mod(which)
            self.pick_random_palette(which)

    # ---- midi channel, upper octave E -------------------------------------

    def next_midi_channel(self):
        ch = self.config["midi_channel"] + 1
        if ch > 16 : ch = 1
        self.config["midi_channel"] = ch
        oled.notify("MIDI Channel", str(ch))
        return ch

    def midi_channel_key(self, pressed):
        """Upper octave E. One channel per press, on the way up.

        Deliberately not a repeater. Holding it does nothing, so a key leaned
        on cannot walk the channel away from you, and the step lands where the
        finger leaves rather than where it arrives.
        """
        if pressed : return
        self.next_midi_channel()
        self.save_config_file()

    def save_or_delete_scene(self, key_stat):
        if key_stat > 0 :
            self.save_key_status = True
            self.save_key_time = time.time()  # start timer
        else :
            if (self.save_key_status) :  # key release before delete happens
                self.save_key_status = False
                self.save_scene()
            self.save_key_status = False
                
    def delete_current_scene(self):
        print("deleting scene")
        if len(self.scenes) > 0:    
            # delete from list and delete folder
            file_path = self.SCENES_PATH + self.scenes[self.scene_index]['name']
            file_operations.delete(file_path)
            print("deleted scene " + file_path)
            del self.scenes[self.scene_index]
            if self.scene_index >= len(self.scenes):
                self.scene_index = len(self.scenes) - 1
            if self.scene_index < 0:  # deleted last scene
                self.scene_index = -1  # no scenes
            else:
                self.recall_scene(self.scene_index)

    def save_scene(self):
        print("Saving scene")
       
        # make scenes dir if no exist
        os.makedirs(self.SCENES_PATH, exist_ok=True)

        # Use zero-padded numbering, e.g. scene-0001 for scene folder
        while True:
            folder_path = os.path.join(self.SCENES_PATH, f"scene-{self.next_numbered_scene:04d}")
            if not os.path.exists(folder_path):
                break
            self.next_numbered_scene += 1
        os.makedirs(folder_path)
        scene_file = os.path.join(folder_path, "scene.json")
        imagepath = os.path.join(folder_path, "scene.jpg")

        new_scene = self._scene_fields()
        self.scenes.append(new_scene)
        
        try:
            with open(scene_file, 'w') as f:
                json.dump(new_scene, f, indent=4)
            print(f"Scene saved to {scene_file}")
        except Exception as e:
            print(f"Failed to save scene file: {e}")

        thumb = pygame.Surface((320, 240))
        pygame.transform.scale(self.screen, (320, 240), thumb)
        pygame.image.save(thumb, imagepath)
        print("saved scene screenshot " + imagepath)

        # if there is a knob sequence playing, save that too
        if self.knob_seq_state == "playing":
            self.knob_seq_save(folder_path)

        # add name and thumbnail fields after saving file (allows user to change scene folder names later)
        self.scenes[-1]["name"] = os.path.basename(folder_path)
        self.scenes[-1]["thumbnail"] = imagepath
        # set to new scene
        self.recall_scene(len(self.scenes) - 1)

    # What a scene stores, in one place so saving a new one and updating an
    # existing one cannot drift apart.
    def _scene_fields(self):
        return {
            "mode": self.mode,
            "knob1": self.knob_base[0],
            "knob2": self.knob_base[1],
            "knob3": self.knob_base[2],
            "knob4": self.knob_base[3],
            "knob5": self.knob_base[4],
            "auto_clear": self.auto_clear,
            "bg_palette": self.bg_palette,
            "fg_palette": self.fg_palette,
            "knob_mod": [
                {"on": self.knob_mod[i],
                 "rate": self.knob_mod_rate[i],
                 "depth": self.knob_mod_depth[i]}
                for i in range(0, 5)
            ],
            # whether the palettes were cycling, the same way knob_mod says
            # whether the knobs were. The palette numbers above are still the
            # ones that were showing, and a scene recalled with this on will
            # move off them within a cycle - which is what the knobs do too.
            "palette_mod": {"fg": self.palette_mod[self.PALETTE_FG],
                            "bg": self.palette_mod[self.PALETTE_BG]},
        }

    # Put the palette wobble back the way a scene had it. Anything missing is
    # off, so scenes written before this existed still load.
    def apply_scene_palette_mod(self, raw):
        if not isinstance(raw, dict):
            raw = {}
        for which, key in ((self.PALETTE_FG, "fg"), (self.PALETTE_BG, "bg")):
            self.palette_mod[which] = raw.get(key) is True
            # a full cycle before the first change, rather than inheriting
            # whatever was left on the clock from the last scene
            if self.palette_mod[which]:
                self.arm_palette_mod(which)

    # Five entries of on, rate and depth. Anything missing or out of range
    # falls back to off at the configured rate, so scenes written before knob
    # modulation existed still load.
    def _validate_scene_knob_mod(self, raw):
        out = []
        for i in range(0, 5):
            entry = {}
            if isinstance(raw, list) and i < len(raw) and isinstance(raw[i], dict):
                entry = raw[i]

            rate = entry.get("rate", self.config["knob_mod_rate"])
            if isinstance(rate, bool) or not isinstance(rate, (int, float)) \
                    or not (0 < rate <= 1):
                rate = self.config["knob_mod_rate"]

            depth = entry.get("depth", self.config["knob_mod_depth"])
            if isinstance(depth, bool) or not isinstance(depth, (int, float)) \
                    or not (0 <= depth <= 1):
                depth = self.config["knob_mod_depth"]

            out.append({"on": entry.get("on") is True,
                        "rate": float(rate), "depth": float(depth)})
        return out

    # Put the modulation back the way a scene had it. The knobs have not moved
    # while the scene was away, so everything has to be picked up again before
    # it takes over, exactly as it is when modulation is switched on by hand.
    def apply_scene_knob_mod(self, entries):
        entries = self._validate_scene_knob_mod(entries)
        for i in range(0, 5):
            self.knob_mod[i] = entries[i]["on"]
            self.knob_mod_rate[i] = entries[i]["rate"]
            self.knob_mod_depth[i] = entries[i]["depth"]
            self.knob_mod_value[i] = 0.0
            self.knob_mod_target[i] = \
                random.uniform(-1.0, 1.0) if self.knob_mod[i] else 0.0
            self.knob_mod_editing[i] = None
            self.knob_mod_unlocked[i] = False
            self.knob_mod_key_held[i] = False
            self.knob_mod_key_used[i] = False

    def update_scene(self):
        print("Updating current scene")

        # Get the current scene
        if not (0 <= self.scene_index < len(self.scenes)):
            print("Invalid scene index. Cannot update.")
            return

        current_scene = self.scenes[self.scene_index]
        folder_name = current_scene["name"]
        folder_path = os.path.join(self.SCENES_PATH, folder_name)

        if not os.path.exists(folder_path):
            print(f"Scene folder {folder_path} does not exist. Cannot update.")
            return

        scene_file = os.path.join(folder_path, "scene.json")
        imagepath = os.path.join(folder_path, "scene.jpg")

        # Create the updated scene dictionary without "name" and "thumbnail"
        updated_scene = self._scene_fields()

        # Update in-memory scene representation, adding computed fields back
        self.scenes[self.scene_index] = {**updated_scene, "name": folder_name, "thumbnail": imagepath}

        try:
            # Save the updated scene to the JSON file, excluding computed fields
            with open(scene_file, 'w') as f:
                json.dump(updated_scene, f, indent=4)
            print(f"Updated scene saved to {scene_file}")
        except Exception as e:
            print(f"Failed to update scene file: {e}")
            return

        # Update the thumbnail image
        thumb = pygame.Surface((320, 240))
        pygame.transform.scale(self.screen, (320, 240), thumb)
        try:
            pygame.image.save(thumb, imagepath)
            print(f"Updated scene screenshot saved to {imagepath}")
        except Exception as e:
            print(f"Failed to save updated thumbnail: {e}")
            return

        # if there is a knob sequence playing, save that too, otherwise erase any previously recorded ones
        if self.knob_seq_state == "playing":
            self.knob_seq_save(folder_path)
        else:
            self.knob_seq_delete_file(folder_path)

        print("Scene updated successfully.")

    def _load_scene(self, folder_path):
        scene_file = os.path.join(folder_path, "scene.json")
        if not os.path.isfile(scene_file):
            print(f"No scene.json in {folder_path}")
            return None
        
        # Load JSON
        try:
            with open(scene_file, 'r') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Failed to read scene.json in {folder_path}: {e}")
            return None
        
        # Validate
        try:
            if not (0 <= float(data["knob1"]) <= 1): print(f"knob1 invalid in {folder_path}"); return None
            if not (0 <= float(data["knob2"]) <= 1): print(f"knob2 invalid in {folder_path}"); return None
            if not (0 <= float(data["knob3"]) <= 1): print(f"knob3 invalid in {folder_path}"); return None
            if not (0 <= float(data["knob4"]) <= 1): print(f"knob4 invalid in {folder_path}"); return None
            if not (0 <= float(data["knob5"]) <= 1): print(f"knob5 invalid in {folder_path}"); return None
            if not isinstance(data["auto_clear"], bool): print(f"auto_clear invalid in {folder_path}"); return None
            if not isinstance(data["mode"], str): print(f"mode invalid in {folder_path}"); return None
            if not (0 <= int(data["bg_palette"])): print(f"bg_palette invalid in {folder_path}"); return None
            if not (0 <= int(data["fg_palette"])): print(f"fg_palette invalid in {folder_path}"); return None
        except Exception as e:
            print(f"Validation error in {folder_path}: {e}")
            return None

        # Build scene dict
        new_scene = {
            "mode": data["mode"],
            "knob1": float(data["knob1"]),
            "knob2": float(data["knob2"]),
            "knob3": float(data["knob3"]),
            "knob4": float(data["knob4"]),
            "knob5": float(data["knob5"]),
            "auto_clear": data["auto_clear"],
            "bg_palette": int(data["bg_palette"]),
            "fg_palette": int(data["fg_palette"]),
            # optional, scenes predating knob modulation simply have it off
            "knob_mod": self._validate_scene_knob_mod(data.get("knob_mod")),
            "name": os.path.basename(folder_path),
            "thumbnail": os.path.join(folder_path, "scene.jpg")
        }
        return new_scene


    def load_scenes(self):
        self.scenes = []
        self.next_numbered_scene = 1
        
        if not os.path.isdir(self.SCENES_PATH):
            print(f"Scenes path {self.SCENES_PATH} does not exist.")
            return
        
        try:
            folders = os.listdir(self.SCENES_PATH)
        except Exception as e:
            print(f"Failed to list {self.SCENES_PATH}: {e}")
            return

        # Determine highest zero-padded "scene-####" number
        for folder in folders:
            if folder.startswith("scene-"):
                try:
                    number = int(folder.replace("scene-", ""))
                    if number >= self.next_numbered_scene:
                        self.next_numbered_scene = number + 1
                except Exception as e:
                    print(f"Bad folder name {folder}: {e}")

        folders.sort()
        for folder in folders:
            folder_path = os.path.join(self.SCENES_PATH, folder)
            if os.path.isdir(folder_path):
                try:
                    scene_data = self._load_scene(folder_path)
                    if scene_data:
                        self.scenes.append(scene_data)
                except Exception as e:
                    print(f"Failed loading scene from {folder_path}: {e}")
        
    # see if scene name is in the current list of scenes
    def _get_scene_index(self, target_name):
        for i, scene in enumerate(self.scenes):
            if scene["name"] == target_name:
                return i
        return -1

    def recall_scene_by_name(self, name) :
        i = self._get_scene_index(name) 
        if i >= 0:
            self.recall_scene(i)
        else:
            print(f"{name} not found")

    def recall_scene(self, index) :
        print("recalling scene " + str(index))

        try :
            scene = self.scenes[index]
            self.scene_index = index
            self.override_all_knobs()
            self.knob[0] = scene["knob1"]
            self.knob[1] = scene["knob2"]
            self.knob[2] = scene["knob3"]
            self.knob[3] = scene["knob4"]
            self.knob[4] = scene["knob5"]
            self.auto_clear = scene["auto_clear"]
            self.bg_palette = scene["bg_palette"]
            self.fg_palette = scene["fg_palette"]
            self.apply_scene_knob_mod(scene.get("knob_mod"))
            self.apply_scene_palette_mod(scene.get("palette_mod"))

            # make sure scenes pallete in range
            if self.fg_palette < 0 : self.fg_palette = 0
            if self.fg_palette >= len(self.palettes) : self.fg_palette = 0
            if self.bg_palette < 0 : self.bg_palette = 0
            if self.bg_palette >= len(self.palettes) : self.bg_palette = 0

            self.set_mode_by_name(scene["mode"])
            # play back knob file if we have one, otherwise stop the seq if running
            if self.knob_seq_load(self.SCENES_PATH + scene["name"]):
                self.knob_seq_play()
            else:
                self.knob_seq_stop()
        except ValueError as e:
            print(f"Problem recalling scene: {e}")
        except Exception as e:
            print(f"Problem recalling scene: {e}")

    def next_scene(self):
        if len(self.scenes) > 0:    
            self.scene_index += 1
            if self.scene_index >= len(self.scenes) : 
                self.scene_index = 0
            self.recall_scene(self.scene_index)

    def prev_scene (self) :
        if len(self.scenes) > 0:    
            self.scene_index -= 1
            if self.scene_index < 0 : 
                if len(self.scenes) > 0 :
                    self.scene_index = len(self.scenes) - 1
                else :
                    self.scene_index = 0
            self.recall_scene(self.scene_index)

    def get_color_from_phase(self, val, palette_index) :
        c = float(val)

        t = c

        ci = palette_index
        ci = ci % len(self.palettes)
        a = self.palettes[ci]["a"]
        b = self.palettes[ci]["b"]
        c = self.palettes[ci]["c"]
        d = self.palettes[ci]["d"]
   
        #print(self.palettes[ci]["name"])
        color = [
            a[i] + b[i] * math.cos(6.283185 * (c[i] * t + d[i]))
            for i in range(3)
        ]
 
        color = (max(0, min(1,color[0])) * 255, max(0, min(1,color[1])) * 255, max(0, min(1,color[2])) * 255)
        return color

    def color_picker( self, val ):
        if not self.palettes_user_defined :
            # first slot legacy color pickers
            if self.fg_palette == 0 : return self.color_picker_original(val)
            return self.get_color_from_phase(val, self.fg_palette)
        else:
            return self.get_color_from_phase(val, self.fg_palette)

    # sets bg_color
    def color_picker_bg( self, val):
        if not self.palettes_user_defined :
            # first slot legacy color pickers
            if self.bg_palette == 0 : 
                self.bg_color = self.color_picker_bg_original(val)          
                return self.bg_color
            self.bg_color = self.get_color_from_phase(val, self.bg_palette)
            return self.bg_color
        else : 
            self.bg_color = self.get_color_from_phase(val, self.bg_palette)
            return self.bg_color

    # returns but doen'st sent bg_color
    def color_picker_bg_preview( self, val):
        if not self.palettes_user_defined :
            # first slot legacy color pickers
            if self.bg_palette == 0 : return self.color_picker_bg_original(val)          
            return self.get_color_from_phase(val, self.bg_palette)
        else:
            return self.get_color_from_phase(val, self.bg_palette)

    # legacy color picker used for first palette slot 
    def color_picker_original( self, val ):
        # convert knob to 0-1
        c = float(val)

        # all the way down random bw
        rando = random.randrange(0, 2)
        color = (rando * 255, rando * 255, rando * 255)

        # random greys
        if c > .02 :
            rando = random.randrange(0,255)
            color = (rando, rando, rando)
        # grey 1
        if c > .04 :
            color = (50, 50, 50)
        # grey 2
        if c > .06 :
            color = (100, 100 ,100)
        # grey 3
        if c > .08 :
            color = (150, 150 ,150)
        # grey 4
        if c > .10 :
            color = (150, 150 ,150)
            
        # grey 5
        if c > .12 :
            color = (200, 200 ,200)
        # white
        if c > .14 :
            color = (250, 250 ,250)
        #colors
        if c > .16 :
            
            #r = float(control) / 1024 * 255
            #g = float((control * 2) % 1024) / 1024 * 255
            #b = float((control * 4) % 1024) / 1024 * 255
            
            r = math.sin(c * 2 * math.pi) * .5 + .5
            g = math.sin(c * 4 * math.pi) * .5 + .5
            b = math.sin(c * 8 * math.pi) * .5 + .5
            color = (r * 255,g * 255,b * 255)
        # full ranoms
        if c > .96 :
            color = (random.randrange(0,255), random.randrange(0,255), random.randrange(0,255))
        # primary randoms
        if c > .98 :
            r = random.randrange(0, 2) * 255
            g = random.randrange(0, 2) * 255
            b = random.randrange(0, 2) * 255
            color = (r,g,b)
        
        color2 = (color[0], color[1], color[2])
        return color2
 
    # legacy color picker used for first palette slot 
    def color_picker_bg_original( self, val):
        c = float(val)
        r = (1 - (math.cos(c * 3 * math.pi) * .5 + .5)) * c
        g = (1 - (math.cos(c * 7 * math.pi) * .5 + .5)) * c
        b = (1 - (math.cos(c * 11 * math.pi) * .5 + .5)) * c
        
        color = (r * 255,g * 255,b * 255)
        
        return color 

    def color_picker_lfo(self, knob_val, inc_amt=.1):
        self.color_lfo_index = (self.color_lfo_index + self.color_lfo_inc) % 2    # ramp 0-2
        if knob_val <= .5:
            return self.color_picker((knob_val * 2) % 1)
        else:
            self.color_lfo_inc = (knob_val - .5) * 2 * inc_amt
            if self.color_lfo_index <= 1: return self.color_picker(self.color_lfo_index)  # ramp up
            else: return self.color_picker(2 - self.color_lfo_index)            # ramp down
                
    def dispatch_key_event(self, k, v):
        
        # the shift key status, also resets all repeater key timers (or not)
        # and does some other stuff when pressed / released
        if k == 2 :
            if v > 0 : 
                self.key2_status = True
                #self.key4_td = 0
                #self.key5_td = 0
                #self.key6_td = 0
                #self.key7_td = 0
                # grab gain knob value so we can check it for movement while shift is down
                self.gain_knob_capture = self.knob_hardware[0]
                self.gain_knob_unlocked = False
                self.gain_value_snapshot = self.config["audio_gain"]
                # same again for the passthrough level on knob 5. the last
                # seen position is cleared as well, so the first move after
                # shift always draws its bar even when the knob happens to
                # have come back to where it was left last time
                self.thru_knob_capture = self.knob_hardware[4]
                self.thru_knob_unlocked = False
                self.thru_knob_last = -1
                self.thru_value_snapshot = self.config["audio_thru_volume"]
            else :
                # save gain to config if changed
                if self.gain_value_snapshot != self.config["audio_gain"] : 
                    v = self.config["audio_gain"]
                    print(f"gain value updated {v}, saving to config")
                    self.save_config_file()
                if self.thru_value_snapshot != self.config["audio_thru_volume"] :
                    v = self.config["audio_thru_volume"]
                    print(f"audio thru level updated {v}, saving to config")
                    self.save_config_file()
                self.key2_status = False
        
        # status of these keys also used for key repeating
        if k == 6 :
            if v > 0 : self.key6_status = True
            else : self.key6_status = False
        if k == 7 :
            if v > 0 : self.key7_status = True
            else : self.key7_status = False
        if k == 4 :
            if v > 0 : self.key4_status = True
            else : self.key4_status = False
        if k == 5 :
            if v > 0 : self.key5_status = True
            else : self.key5_status = False
        if k == 10 :
            if v > 0 : self.key10_status = True
            else : self.key10_status = False

        # toggle osd or menu depending on shift
        if (k == 1 and v > 0) : 
            if self.key2_status: self.toggle_menu()
            else : self.toggle_osd()
       
        # set key press events for menu navigation
        if self.menu_mode :
            if (k == 2 and v > 0) : self.key2_press = True
            if (k == 3 and v > 0) : self.key3_press = True
            if (k == 4 and v > 0) : self.key4_press = True
            if (k == 5 and v > 0) : self.key5_press = True
            if (k == 6 and v > 0) : self.key6_press = True
            if (k == 7 and v > 0) : self.key7_press = True
            if (k == 8 and v > 0) : self.key8_press = True
            if (k == 9 and v > 0) : self.key9_press = True
            if (k == 10 and v > 0) : self.key10_press = True
        # in regular mode, check if shift button is down
        # some keys also have repeater, so we reset those timers when keys presssed
        else :
            if self.key2_status :  
                if (k == 4 and v > 0) : 
                    self.prev_fg_palette()
                    self.key4_td = 0
                if (k == 5 and v > 0) : 
                    self.next_fg_palette()
                    self.key5_td = 0
                if (k == 6 and v > 0) : 
                    self.prev_bg_palette()
                    self.key6_td = 0
                if (k == 7 and v > 0) : 
                    self.next_bg_palette()
                    self.key7_td = 0
                if (k == 8 and v > 0) : self.update_scene()
                if (k == 9 and v > 0) : self.knob_seq_play_stop_key()
                if (k == 10 and v > 0) : self.knob_seq_record_key()
            else :
                if (k == 3 and v > 0) : self.toggle_auto_clear()
                if (k == 4 and v > 0) : 
                    self.prev_mode()
                    self.key4_td = 0
                if (k == 5 and v > 0) : 
                    self.next_mode()
                    self.key5_td = 0
                if (k == 6 and v > 0) : 
                    self.prev_scene()
                    self.key6_td = 0
                if (k == 7 and v > 0) : 
                    self.next_scene()
                    self.key7_td = 0
                if (k == 8)           : self.save_or_delete_scene(v)
                if (k == 9 and v > 0) : self.screengrab_flag = True
                if (k == 10 and v > 0) : 
                    self.trig = True
                    self.key10_td = 0

    def update_key_repeater(self) :
       # if self.key10_status :
       #     self.trig = True
        if not self.menu_mode :
            if self.key2_status : 
                if self.key4_status :
                    self.key4_td += 1
                    if (self.key4_td > 10) : self.prev_fg_palette()
                if self.key5_status :
                    self.key5_td += 1
                    if (self.key5_td > 10) : self.next_fg_palette()
                if self.key6_status :
                    self.key6_td += 1
                    if (self.key6_td > 10) : self.prev_bg_palette()
                if self.key7_status :
                    self.key7_td += 1
                    if (self.key7_td > 10) : self.next_bg_palette()
            else :
                if self.key4_status :
                    self.key4_td += 1
                    if (self.key4_td > 10) : self.prev_mode()
                if self.key5_status :
                    self.key5_td += 1
                    if (self.key5_td > 10) : self.next_mode()
                if self.key6_status :
                    self.key6_td += 1
                    if (self.key6_td > 10) : self.prev_scene()
                if self.key7_status :
                    self.key7_td += 1
                    if (self.key7_td > 10) : self.next_scene()
                if self.key10_status :
                    self.key10_td += 1
                    if (self.key10_td > 10) : self.trig = True
    
    def check_gain_knob(self):
        if self.key2_status:
            if abs(self.gain_knob_capture - self.knob_hardware[0]) > .05: self.gain_knob_unlocked = True
            if self.gain_knob_unlocked:
                self.config["audio_gain"] = self.knob_hardware[0]

    # Shift and the volume knob set how loud the line input is passed straight
    # through to the line output. Knob 5 is the one the panel prints "Volume"
    # on, and shift is the only time it is not busy being a mode parameter.
    #
    # It has to be moved a little before it takes hold, the same way the gain
    # knob does. On an output amp that matters more than it does on the gain:
    # without it, pressing shift would jump the level to wherever the knob was
    # left sitting, which is as likely to be full as it is to be silent.
    def check_thru_knob(self):
        if not self.key2_status:
            return

        if abs(self.thru_knob_capture - self.knob_hardware[4]) > .05:
            self.thru_knob_unlocked = True
        if not self.thru_knob_unlocked:
            return

        # a knob that has not moved needs neither an amp write nor a
        # notification, and at sixty frames a second there would be plenty
        if self.knob_hardware[4] == self.thru_knob_last:
            return
        self.thru_knob_last = self.knob_hardware[4]

        v = self.knob_hardware[4]
        self.config["audio_thru_volume"] = v
        audio_thru.set_volume(v)
        oled.notify_value("Audio Thru", v)

    def set_led(self, val):
        self.led = val
        self.new_led = True

    def knob_seq_play_stop_key(self):
        if self.knob_seq_state == "playing": 
            self.knob_seq_stop()
        elif self.knob_seq_state == "recording":
            self.knob_seq_play()
        elif self.knob_seq_state == "stopped":
            self.knob_seq_play()
        elif self.knob_seq_state == "enabled":
            self.knob_seq_stop()


    def knob_seq_record_key(self):
        if self.knob_seq_state == "playing":
            self.knob_seq_record_enable()
        elif self.knob_seq_state == "recording":
            self.knob_seq_play()
        elif self.knob_seq_state == "stopped":
            self.knob_seq_record_enable()
        elif self.knob_seq_state == "enabled":
            self.knob_seq_stop()

   
    # The sequencer and the wobble both write the same five knobs, so they
    # cannot both be running. The key refuses to start a wobble during
    # playback; this is the other direction, and it sits here because every
    # route into playing goes through this one call — including recalling a
    # scene, which applies its modulation before it loads its sequence.
    def stop_all_knob_mod(self):
        for i in range(0, 5):
            if not self.knob_mod[i] : continue
            self.knob_mod[i] = False
            self.knob_mod_value[i] = 0.0
            self.knob_mod_editing[i] = None
            # hold the value until the knob is moved, as switching off by hand does
            self.knob_override[i] = True
            self.knob_snapshot[i] = self.knob_hardware[i]

    def knob_seq_play(self):
        self.stop_all_knob_mod()
        self.knob_seq_state = "playing"
        self.knob_seq_index = 0
        print("knob sequence playing")
        self.set_led(3)

    def knob_seq_record(self):
        self.knob_seq_state = "recording"
        self.knob_seq = []
        self.knob_seq_index = 0
        print("knob sequence recording")
        self.set_led(1)

    def knob_seq_stop(self):
        self.knob_seq_state = "stopped"
        print("knob sequence stopping")
        self.set_led(7)

    def knob_seq_record_enable(self):
        # snapshot current knob 
        self.knob_seq_last_values[:] = self.knob[:]
        self.knob_seq_state = "enabled"
        print(f"knob sequence record enabled")
        self.set_led(6)


    def knob_seq_run(self):
        if self.knob_seq_state == "stopped":
            return

        elif self.knob_seq_state == "enabled":
            moved = any(abs(x-y) >= .005 for x,y in zip(self.knob_seq_last_values, self.knob))
            if moved: self.knob_seq_record()

        elif self.knob_seq_state == "recording":
            frame_values = tuple(self.knob)  # Collect current knob values
            self.knob_seq.append(frame_values)
            
            # Auto stop after maximum frames
            MAX_FRAMES = 1000
            if len(self.knob_seq) > MAX_FRAMES:
                self.knob_seq_play()

        elif self.knob_seq_state == "playing":
            if self.knob_seq:
                current_values = self.knob_seq[self.knob_seq_index]
                
                # Update knobs only on value change
                for i, value in enumerate(current_values):
                    if value != self.knob_seq_last_values[i]:
                        self.knob_seq_last_values[i] = value
                        self.knob[i] = value

                # Increment and wrap playback index
                self.knob_seq_index += 1
                if self.knob_seq_index >= len(self.knob_seq):
                    self.knob_seq_index = 0
            else:
                self.knob_seq_stop()

    def knob_seq_save(self, path):
        """Saves the knob_seq list to a JSON file."""
        try:
            file_path = os.path.join(path, "knob_seq.json")
            # Write the knob_seq list to the file
            with open(file_path, "w") as file:
                json.dump(self.knob_seq, file)
            return True
        except Exception as e:
            print(f"Error saving knob_seq: {e}")
            return False

    def knob_seq_load(self, path):
        """Loads the knob_seq list from a JSON file."""
        try:
            file_path = os.path.join(path, "knob_seq.json")
            
            # Check if the file exists
            if not os.path.isfile(file_path):
                print(file_path + " does not exist.")
                return False

            # Read and load the JSON file
            with open(file_path, "r") as file:
                data = json.load(file)

            # Validate the data
            if isinstance(data, list) and all(isinstance(frame, (list, tuple)) for frame in data):
                self.knob_seq = data
                return True
            else:
                print("Invalid JSON structure for knob_seq.")
                return False
        except json.JSONDecodeError:
            print("Error decoding JSON file.")
            return False
        except Exception as e:
            print(f"Error loading knob_seq: {e}")
            return False

    def knob_seq_delete_file(self, path):
        """Deletes the knob_seq.json file at the specified path."""
        try:
            file_path = os.path.join(path, "knob_seq.json")
            
            # Check if the file exists
            if os.path.isfile(file_path):
                os.remove(file_path)  # Delete the file
                print(f"knob seq file {file_path} deleted successfully.")
                return True
            else:
                print(f"knob seq file {file_path} does not exist.")
                return False
        except Exception as e:
            print(f"error deleting knob seq file {file_path}: {e}")
            return False

    def clear_flags(self):
        self.new_midi = False
        self.trig = False
        self.run_setup = False
        self.screengrab_flag = False
        self.midi_note_new = False
        for i in range(0, 128):
            self.midi_notes_last[i] = self.midi_notes[i]
        self.key1_press = False
        self.key2_press = False
        self.key3_press = False
        self.key4_press = False
        self.key5_press = False
        self.key6_press = False
        self.key7_press = False
        self.key8_press = False
        self.key9_press = False
        self.key10_press = False
        self.new_led = False
        self.encoder_turn = 0
        self.encoder_press = False

