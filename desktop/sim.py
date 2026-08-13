#!/usr/bin/env python3
"""EYESY mode simulator for macOS.

Runs the instrument's own video engine against a folder of modes on a Mac and
puts the picture, the controls and a source editor in a browser, so a mode can
be written and heard reacting to audio without an EYESY on the desk.

The engine is used unmodified. Everything the instrument has and a laptop does
not — ALSA, MIDI over OSC, the Organelle OLED, the panel hardware — is either
stubbed (stubs/liblo.py) or simply never started, and oled.py disables itself
off the instrument anyway.

    pygame render loop  ── main thread, because macOS insists ──┐
      1280x720, 30fps                                           │
            ▲                                                   ▼
      command queue                                    sim_video.FrameStream
            │                                                   │
      Flask (daemon thread) ◀── browser ──▶ /stream.mjpg ◀───────┘
            ▲
      sim_audio.AudioInput ◀── CoreAudio ◀── microphone

The web thread never touches engine state directly: it queues a callable that
the render loop runs between frames. Reads of single values for the status
poll go straight through, which the GIL makes safe enough.
"""

import argparse
import json
import math
import os
import queue
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.abspath(os.path.join(HERE, "..", "engines", "python"))

# stubs ahead of everything, so the engine's `import liblo` finds ours
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ENGINE_DIR)

# oled.py and organelle.py are no-ops unless this says otherwise, and it must
# not say otherwise here
os.environ.pop("EYESY_PLATFORM", None)

# font.ttf, ./font.ttf and friends are loaded relative to the working
# directory all over the engine, the same way the service runs on the device
os.chdir(ENGINE_DIR)

DEFAULT_MODES_PATH = os.path.expanduser(
    "~/work/EYESY_on_Organelle/EYESY_Modes")
STATE_DIR = os.path.expanduser("~/.eyesy_sim")
SETTINGS_PATH = os.path.join(STATE_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "modes_path": DEFAULT_MODES_PATH,
    "audio_device": None,
    "stream_width": 640,
    "stream_fps": 20,
    "stream_smooth": True,
    "port": 8080,
}


def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH) as f:
            settings.update(json.load(f))
    except (OSError, ValueError):
        pass
    return settings


def save_settings(settings):
    os.makedirs(STATE_DIR, exist_ok=True)
    try:
        with open(SETTINGS_PATH, "w") as f:
            json.dump(settings, f, indent=2)
    except OSError as e:
        print(f"could not save settings: {e}")


class Simulator:
    """Owns the engine, the render loop and everything the web app pokes at."""

    def __init__(self, settings, show_window=False):
        self.settings = settings
        self.show_window = show_window

        self.commands = queue.Queue()
        self.mode_errors = {}
        self.running = True

        self.eyesy = None
        self.audio = None
        self.stream = None
        self.hwscreen = None
        self.mode_screen = None

        self._setup_done = set()
        self._undulate_p = 0.0
        self._fps_start = time.time()

    # ---- startup ---------------------------------------------------------

    def start(self):
        import pygame

        import sim_audio
        import sim_video

        self.pygame = pygame

        eyesy_module = __import__("eyesy")
        etc = eyesy_module.Eyesy()

        modes_path = self.settings["modes_path"].rstrip("/") + "/"
        etc.MODES_PATH = modes_path
        etc.GRABS_PATH = os.path.join(STATE_DIR, "Grabs") + "/"
        etc.SCENES_PATH = os.path.join(STATE_DIR, "Scenes") + "/"
        etc.SYSTEM_PATH = os.path.join(STATE_DIR, "System") + "/"

        etc.ensure_directories()
        etc.load_config_file()
        etc.load_palettes()

        self.eyesy = etc

        pygame.init()
        pygame.mouse.set_visible(False)
        self.clocker = pygame.time.Clock()
        print("pygame version " + pygame.version.ver)

        flags = 0 if self.show_window else pygame.HIDDEN
        self.hwscreen = pygame.display.set_mode(etc.RES, flags)
        pygame.display.set_caption("EYESY simulator")
        etc.xres = self.hwscreen.get_width()
        etc.yres = self.hwscreen.get_height()
        print(f"screen {etc.xres}x{etc.yres}")

        self.mode_screen = pygame.Surface((etc.xres, etc.yres))
        etc.screen = self.mode_screen
        self.hwscreen.fill((0, 0, 0))
        pygame.display.flip()

        etc.font = pygame.font.Font("font.ttf", 16)

        self.load_modes()
        etc.load_grabs()
        etc.load_scenes()

        self._init_menu_screens()

        if etc.mode_names:
            self.select_mode_index(0)

        self.audio = sim_audio.AudioInput()
        self.audio.start(self.settings.get("audio_device"))

        self.stream = sim_video.FrameStream(
            width=self.settings.get("stream_width", 640),
            fps=self.settings.get("stream_fps", 20),
            smooth=self.settings.get("stream_smooth", True))

    def _init_menu_screens(self):
        """The instrument's settings menus, for whichever of them import."""
        etc = self.eyesy
        wanted = [
            ("home", "screen_main_menu", "ScreenMainMenu"),
            ("test", "screen_test", "ScreenTest"),
            ("video_settings", "screen_video_settings", "ScreenVideoSettings"),
            ("palette", "screen_palette", "ScreenPalette"),
            ("midi_settings", "screen_midi_settings", "ScreenMIDISettings"),
            ("midi_pc_mapping", "screen_midi_pc_mapping", "ScreenMIDIPCMapping"),
            ("applogs", "screen_applogs", "ScreenApplogs"),
            ("wifi", "screen_wifi", "ScreenWiFi"),
        ]
        for key, module_name, class_name in wanted:
            try:
                module = __import__(module_name)
                etc.menu_screens[key] = getattr(module, class_name)(etc)
            except Exception as e:
                print(f"menu screen {key} unavailable: {e}")
        if "home" in etc.menu_screens:
            etc.switch_menu_screen("home")

    def load_modes(self):
        """Like eyesy.load_modes, but it remembers why a mode did not load.

        The engine's version prints tracebacks and moves on, which is right on
        an instrument mid set and useless when the whole point is finding out
        what is wrong with the mode being written.
        """
        import imp

        import helpers

        etc = self.eyesy
        etc.mode_names = []
        self.mode_errors = {}
        self._setup_done = set()

        folders = sorted(helpers.get_immediate_subdirectories(etc.MODES_PATH),
                         key=lambda s: s.lower())
        for name in folders:
            if name.startswith("."):
                continue
            path = os.path.join(etc.MODES_PATH, name, "main.py")
            if not os.path.exists(path):
                continue
            try:
                imp.load_source(name, path)
                etc.mode_names.append(name)
            except Exception:
                self.mode_errors[name] = traceback.format_exc()

        print(f"loaded {len(etc.mode_names)} modes, "
              f"{len(self.mode_errors)} failed")
        return len(etc.mode_names) > 0

    # ---- things the web app asks for, run on the render thread -----------

    def submit(self, fn):
        self.commands.put(fn)

    def select_mode_index(self, index):
        etc = self.eyesy
        if not etc.mode_names:
            return
        index = max(0, min(index, len(etc.mode_names) - 1))
        etc.set_mode_by_index(index)
        # the instrument runs every mode's setup at startup; here it is done
        # on first use, so 67 modes do not have to be paid for up front
        if etc.mode in self._setup_done:
            etc.error = ""
        else:
            etc.run_setup = True

    def select_mode_name(self, name):
        etc = self.eyesy
        if name in etc.mode_names:
            self.select_mode_index(etc.mode_names.index(name))

    def reload_mode(self, name=None):
        """Re-import a mode after an edit, and pick up ones that were broken.

        A mode whose main.py does not import is not in mode_names at all, so
        this is also the path back in for one that has just been fixed in the
        editor — which is most of what the editor is for.
        """
        etc = self.eyesy
        name = name or etc.mode

        if name not in etc.mode_names:
            import imp

            path = os.path.join(etc.MODES_PATH, name, "main.py")
            if not os.path.exists(path):
                return
            try:
                imp.load_source(name, path)
            except Exception:
                self.mode_errors[name] = traceback.format_exc()
                return
            self.mode_errors.pop(name, None)
            etc.mode_names.append(name)
            etc.mode_names.sort(key=lambda s: s.lower())
            self._setup_done.discard(name)
            self.select_mode_name(name)
            return

        etc.set_mode_by_index(etc.mode_names.index(name))
        self._setup_done.discard(name)
        self.mode_errors.pop(name, None)
        etc.reload_mode()
        if etc.error:
            self.mode_errors[name] = etc.error

    def rescan_modes(self, modes_path=None):
        etc = self.eyesy
        current = etc.mode
        if modes_path:
            etc.MODES_PATH = modes_path.rstrip("/") + "/"
            self.settings["modes_path"] = etc.MODES_PATH
            save_settings(self.settings)
        self.load_modes()
        if current in etc.mode_names:
            self.select_mode_name(current)
        elif etc.mode_names:
            self.select_mode_index(0)

    def set_knob(self, index, value):
        # knob_hardware is what the panel would drive; going through it keeps
        # the override and knob sequencer logic behaving as on the instrument
        self.eyesy.knob_hardware[index] = max(0.0, min(1.0, float(value)))

    def key(self, k, v):
        self.eyesy.dispatch_key_event(int(k), int(v))

    def set_audio_device(self, index):
        ok = self.audio.start(index)
        if ok:
            self.settings["audio_device"] = index
            save_settings(self.settings)
        return ok

    def configure_stream(self, width=None, fps=None, smooth=None):
        self.stream.configure(width=width, fps=fps, smooth=smooth)
        self.settings["stream_width"] = self.stream.width
        self.settings["stream_fps"] = self.stream.fps
        self.settings["stream_smooth"] = self.stream.smooth
        save_settings(self.settings)

    # ---- render loop -----------------------------------------------------

    def _drain_commands(self):
        while True:
            try:
                fn = self.commands.get_nowait()
            except queue.Empty:
                return
            try:
                fn()
            except Exception:
                print("command failed:\n" + traceback.format_exc())

    def _handle_window_events(self):
        pygame = self.pygame
        key_map = {pygame.K_1: 1, pygame.K_2: 2, pygame.K_3: 3, pygame.K_4: 4,
                   pygame.K_5: 5, pygame.K_6: 6, pygame.K_7: 7, pygame.K_8: 8,
                   pygame.K_9: 9, pygame.K_0: 10}
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type in (pygame.KEYDOWN, pygame.KEYUP):
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key in key_map:
                    self.eyesy.dispatch_key_event(
                        key_map[event.key],
                        1 if event.type == pygame.KEYDOWN else 0)

    def _read_audio(self):
        """The audio half of main.py's loop, same numbers, same trigger."""
        etc = self.eyesy

        if etc.audio_muted:
            for i in range(len(etc.audio_in)):
                etc.audio_in[i] = 0
                etc.audio_in_r[i] = 0
            etc.audio_peak = 0
            etc.audio_peak_r = 0
        elif not etc.key10_status:
            with self.audio.lock:
                etc.audio_in[:] = self.audio.buffer[:]
                etc.audio_in_r[:] = self.audio.buffer_r[:]
                g = etc.config["audio_gain"]
                self.audio.gain = float((g * g * 50) + 1)
                etc.audio_peak = self.audio.peak
                etc.audio_peak_r = self.audio.peak_r
                if etc.config["trigger_source"] in (0, 2):
                    if etc.audio_peak > 20000 or etc.audio_peak_r > 20000:
                        etc.trig = True
        else:
            # trigger button held: the instrument's simulated tone, so a mode
            # can be checked with no audio playing at all
            if not etc.menu_mode:
                self._undulate_p += .005
                undulate = ((math.sin(self._undulate_p * 2 * math.pi) + 1) * 2) + .5
                for i in range(len(etc.audio_in)):
                    etc.audio_in[i] = int(
                        math.sin((i / 100) * 2 * math.pi * undulate) * 25000)
                    etc.audio_in_r[i] = etc.audio_in[i]
                etc.audio_peak = 25000
                etc.audio_peak_r = 25000

    def run(self):
        import osd

        pygame = self.pygame
        etc = self.eyesy

        while self.running:
            try:
                self._drain_commands()
                self._handle_window_events()

                etc.update_knobs_and_notes()
                etc.update_key_repeater()
                etc.check_gain_knob()
                etc.knob_seq_run()
                etc.set_knobs()

                etc.frame_count += 1
                if (etc.frame_count % 30) == 0:
                    now = time.time()
                    etc.fps = 1 / ((now - self._fps_start) / 30)
                    self._fps_start = now

                self._read_audio()

                mode = None
                try:
                    mode = sys.modules[etc.mode]
                except KeyError:
                    etc.error = f"Mode {etc.mode} not loaded, probably has errors."
                    pygame.time.wait(200)

                if etc.screengrab_flag:
                    etc.screengrab()

                etc.update_scene_save_key()

                if etc.auto_clear and not etc.freeze:
                    self.mode_screen.fill(etc.bg_color)

                if etc.run_setup and mode is not None:
                    etc.error = ""
                    try:
                        mode.setup(self.hwscreen, etc)
                        self._setup_done.add(etc.mode)
                        self.mode_errors.pop(etc.mode, None)
                    except Exception:
                        etc.error = traceback.format_exc()
                        self.mode_errors[etc.mode] = etc.error
                        print("error with setup: " + etc.error)

                if not etc.menu_mode:
                    if not etc.freeze and mode is not None:
                        try:
                            mode.draw(self.mode_screen, etc)
                        except Exception:
                            etc.error = traceback.format_exc()
                            self.mode_errors[etc.mode] = etc.error
                            print("error with draw: " + etc.error)
                            pygame.time.wait(200)
                    self.hwscreen.blit(self.mode_screen, (0, 0))

                if etc.show_osd and not etc.menu_mode:
                    try:
                        osd.render_overlay_480(self.hwscreen, etc)
                    except Exception:
                        etc.error = traceback.format_exc()
                        print("error with OSD: " + etc.error)
                        pygame.time.wait(200)

                if etc.menu_mode:
                    try:
                        etc.current_screen.handle_events()
                        etc.current_screen.render_with_title(self.hwscreen)
                    except Exception:
                        etc.error = traceback.format_exc()
                        print("error with Menu: " + etc.error)
                        pygame.time.wait(200)
                    if etc.restart:
                        # a resolution change on the instrument restarts the
                        # service; here it just takes effect next launch
                        etc.restart = False
                    if not etc.menu_mode:
                        self.hwscreen.fill(etc.bg_color)

                pygame.display.flip()

                # the display rather than the mode surface, so the browser
                # shows the OSD and the menus too — on the instrument those
                # are deliberately kept off the projector, but here they are
                # part of what is being simulated
                self.stream.publish(self.hwscreen)

                etc.clear_flags()

            except Exception:
                etc.clear_flags()
                etc.error = traceback.format_exc()
                print("problem in main loop\n" + etc.error)
                pygame.time.wait(200)

            self.clocker.tick(30)

        self.shutdown()

    def shutdown(self):
        print("shutting down")
        if self.audio:
            self.audio.stop()
        try:
            self.pygame.display.quit()
            self.pygame.quit()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--modes", help="folder of mode folders")
    ap.add_argument("--port", type=int, help="web app port")
    ap.add_argument("--window", action="store_true",
                    help="also open a native pygame window")
    ap.add_argument("--no-browser", action="store_true",
                    help="do not open a browser on startup")
    args = ap.parse_args()

    settings = load_settings()
    if args.modes:
        settings["modes_path"] = os.path.abspath(os.path.expanduser(args.modes))
    if args.port:
        settings["port"] = args.port
    save_settings(settings)

    sim = Simulator(settings, show_window=args.window)
    sim.start()

    import sim_web
    port = settings.get("port", 8080)
    app = sim_web.create_app(sim)

    server = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False,
                               threaded=True, use_reloader=False),
        daemon=True)
    server.start()

    url = f"http://127.0.0.1:{port}/"
    print(f"\n  EYESY simulator on {url}\n")
    if not args.no_browser:
        import webbrowser
        webbrowser.open(url)

    try:
        sim.run()
    except KeyboardInterrupt:
        sim.shutdown()


if __name__ == "__main__":
    main()
