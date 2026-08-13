"""The browser half of the simulator.

Nothing here touches engine state that the render loop writes to: anything
with a side effect is queued as a callable and run between frames. Reading
single values for the status poll goes straight through, which under the GIL
cannot tear.

Localhost only, but paths coming from the editor are still resolved and
checked against the modes folder before anything is written — a mistyped mode
name should not be able to overwrite something else.
"""

import os
import subprocess

from flask import (Flask, Response, jsonify, request, send_from_directory)

import sim_audio

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(HERE, "static")
# the editor is the same Ace build the instrument's web app ships
ACE_DIR = os.path.abspath(
    os.path.join(HERE, "..", "web", "static", "ace", "src-min-noconflict"))

STREAM_BOUNDARY = b"eyesyframe"


def create_app(sim):
    app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
    etc = sim.eyesy

    def mode_dir(name):
        """Absolute path of a mode folder, or None if it is not one of ours.

        Checked against the folder rather than against mode_names, because a
        mode that failed to import is not in mode_names and is exactly the one
        someone wants to open in the editor.
        """
        if not name or os.sep in name or name.startswith("."):
            return None
        root = os.path.realpath(etc.MODES_PATH)
        path = os.path.realpath(os.path.join(root, name))
        if not path.startswith(root + os.sep) or not os.path.isdir(path):
            return None
        return path

    def mode_file(name, filename):
        """Absolute path of a file inside a mode folder, or None."""
        folder = mode_dir(name)
        if folder is None:
            return None
        path = os.path.realpath(os.path.join(folder, filename))
        if not path.startswith(folder + os.sep):
            return None
        return path

    # ---- pages ----------------------------------------------------------

    @app.route("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.route("/ace/<path:filename>")
    def ace(filename):
        return send_from_directory(ACE_DIR, filename)

    # ---- video ----------------------------------------------------------

    @app.route("/stream.mjpg")
    def stream_mjpg():
        return Response(
            sim.stream.frames(STREAM_BOUNDARY),
            mimetype=f"multipart/x-mixed-replace; "
                     f"boundary={STREAM_BOUNDARY.decode()}",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate",
                     "Pragma": "no-cache"})

    @app.route("/frame.jpg")
    def frame_jpg():
        payload = sim.stream.latest()
        if payload is None:
            return "no frame yet", 503
        return Response(payload, mimetype="image/jpeg",
                        headers={"Cache-Control": "no-store"})

    # ---- state ----------------------------------------------------------

    @app.route("/api/state")
    def state():
        return jsonify({
            "modes_path": etc.MODES_PATH,
            "modes": etc.mode_names,
            "mode": etc.mode,
            "mode_index": etc.mode_index,
            "mode_errors": sim.mode_errors,
            "error": etc.error,
            "res": [etc.xres, etc.yres],
            "fps": round(etc.fps, 1),
            "knobs": [round(v, 4) for v in etc.knob],
            "knob_override": list(etc.knob_override),
            "flags": {
                "auto_clear": etc.auto_clear,
                "osd": etc.show_osd,
                "menu": etc.menu_mode,
                "freeze": etc.freeze,
                "audio_muted": etc.audio_muted,
                "shift": etc.key2_status,
            },
            "palette": {"fg": etc.fg_palette, "bg": etc.bg_palette,
                        "count": len(etc.palettes)},
            "audio": {
                "device": sim.audio.device,
                "name": sim.audio.device_name,
                "running": sim.audio.running,
                "samplerate": sim.audio.samplerate,
                "error": sim.audio.error,
                "peak": round(etc.audio_peak, 1),
                "peak_r": round(etc.audio_peak_r, 1),
                "gain": etc.config.get("audio_gain", 0.25),
                "trigger_source": etc.config.get("trigger_source", 0),
            },
            "stream": {
                "width": sim.stream.width,
                "fps": sim.stream.fps,
                "smooth": sim.stream.smooth,
                "encode_ms": round(sim.stream.encode_ms, 2),
                "publish_ms": round(sim.stream.publish_ms, 2),
            },
        })

    # ---- controls -------------------------------------------------------

    @app.route("/api/mode", methods=["POST"])
    def set_mode():
        name = (request.get_json(silent=True) or {}).get("name")
        sim.submit(lambda: sim.select_mode_name(name))
        return jsonify(ok=True)

    @app.route("/api/reload", methods=["POST"])
    def reload_mode():
        name = (request.get_json(silent=True) or {}).get("name")
        sim.submit(lambda: sim.reload_mode(name))
        return jsonify(ok=True)

    @app.route("/api/knob", methods=["POST"])
    def knob():
        data = request.get_json(silent=True) or {}
        index = int(data.get("index", 0))
        value = float(data.get("value", 0))
        if 0 <= index < 5:
            sim.submit(lambda: sim.set_knob(index, value))
        return jsonify(ok=True)

    @app.route("/api/key", methods=["POST"])
    def key():
        data = request.get_json(silent=True) or {}
        k = int(data.get("k", 0))
        v = int(data.get("v", 0))
        if 1 <= k <= 10:
            sim.submit(lambda: sim.key(k, v))
        return jsonify(ok=True)

    @app.route("/api/gain", methods=["POST"])
    def gain():
        value = float((request.get_json(silent=True) or {}).get("value", .25))
        value = max(0.0, min(1.0, value))

        def apply():
            etc.config["audio_gain"] = value
            etc.save_config_file()

        sim.submit(apply)
        return jsonify(ok=True)

    @app.route("/api/trigger_source", methods=["POST"])
    def trigger_source():
        value = int((request.get_json(silent=True) or {}).get("value", 0))
        value = max(0, min(len(etc.TRIGGER_SOURCES) - 1, value))

        def apply():
            etc.config["trigger_source"] = value
            etc.save_config_file()

        sim.submit(apply)
        return jsonify(ok=True)

    # ---- audio ----------------------------------------------------------

    @app.route("/api/audio/devices")
    def audio_devices():
        return jsonify(devices=sim_audio.list_input_devices(),
                       current=sim.audio.device)

    @app.route("/api/audio/device", methods=["POST"])
    def audio_device():
        index = (request.get_json(silent=True) or {}).get("index")
        ok = sim.set_audio_device(None if index is None else int(index))
        return jsonify(ok=ok, error=sim.audio.error)

    # ---- stream ---------------------------------------------------------

    @app.route("/api/stream", methods=["POST"])
    def stream_settings():
        data = request.get_json(silent=True) or {}
        sim.configure_stream(width=data.get("width"), fps=data.get("fps"),
                             smooth=data.get("smooth"))
        return jsonify(ok=True)

    # ---- modes folder ---------------------------------------------------

    @app.route("/api/modes_path", methods=["POST"])
    def modes_path():
        path = (request.get_json(silent=True) or {}).get("path", "")
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isdir(path):
            return jsonify(ok=False, error=f"not a folder: {path}"), 400
        sim.submit(lambda: sim.rescan_modes(path))
        return jsonify(ok=True, path=path)

    @app.route("/api/rescan", methods=["POST"])
    def rescan():
        sim.submit(lambda: sim.rescan_modes())
        return jsonify(ok=True)

    @app.route("/api/choose_folder", methods=["POST"])
    def choose_folder():
        """Native folder picker.

        A browser folder input deliberately never reveals a real path, and the
        engine needs one, so the dialog comes from the Mac itself.
        """
        script = ('tell application "System Events" to activate\n'
                  'POSIX path of (choose folder with prompt '
                  '"Select your EYESY Modes folder")')
        try:
            out = subprocess.run(["osascript", "-e", script],
                                 capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            return jsonify(ok=False, error="folder picker timed out"), 408

        path = out.stdout.strip()
        if out.returncode != 0 or not path:
            # cancelling is not an error worth showing
            return jsonify(ok=False, cancelled=True)

        path = os.path.abspath(path)
        sim.submit(lambda: sim.rescan_modes(path))
        return jsonify(ok=True, path=path)

    # ---- source editing -------------------------------------------------

    @app.route("/api/files")
    def files():
        folder = mode_dir(request.args.get("mode"))
        if folder is None:
            return jsonify(ok=False, error="unknown mode"), 404
        names = sorted(f for f in os.listdir(folder) if f.endswith(".py"))
        return jsonify(ok=True, files=names)

    @app.route("/api/source")
    def get_source():
        path = mode_file(request.args.get("mode"),
                         request.args.get("file", "main.py"))
        if path is None or not os.path.exists(path):
            return jsonify(ok=False, error="no such file"), 404
        with open(path, encoding="utf-8", errors="replace") as f:
            return jsonify(ok=True, content=f.read())

    @app.route("/api/source", methods=["POST"])
    def save_source():
        data = request.get_json(silent=True) or {}
        name = data.get("mode")
        path = mode_file(name, data.get("file", "main.py"))
        if path is None:
            return jsonify(ok=False, error="no such file"), 404

        content = data.get("content")
        if content is None:
            return jsonify(ok=False, error="no content"), 400

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        if data.get("reload", True):
            sim.submit(lambda: sim.reload_mode(name))
        return jsonify(ok=True)

    return app
