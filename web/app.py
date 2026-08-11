import os
import sys
import time
from flask import Flask, request, make_response, jsonify, send_from_directory, send_file, Response
from flask_sock import Sock
import subprocess
import urllib.parse
import werkzeug
import mimetypes
import liblo
import file_operations

# the video engine and the encoder pass frames through /dev/shm
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "engines", "python"))
import framebus

# osc to eyesy app
try:
	osc_target = liblo.Address(4000)
except liblo.AddressError as err:
	print(err)
	sys.exit()

app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = 'secret!'
sock = Sock(app)  # Use Flask-Sock for WebSockets

def background_thread(ws):
    cmd = ["journalctl", "-f", "-u", "eyesypy.service", "-o", "cat"]
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as p:
        try:
            for line in iter(p.stdout.readline, b''):
                decoded_line = line.decode()
                if "(snd_pcm_recover) underrun occurred" in decoded_line:
                    continue  # Skip lines with ALSA underrun errors
                
                try:
                    ws.send(decoded_line)  # Send filtered output over WebSocket
                except:
                    print("WebSocket disconnected. Stopping journalctl...")
                    break  # Exit the loop when the WebSocket is closed
        finally:
            p.terminate()  # Forcefully stop journalctl
            p.wait()       # Ensure process is fully terminated
            print("journalctl process terminated.")

@app.route('/test')
def test():
    return "asdf"

@app.route('/stop_video_engine')
def stop_video_engine():
    print("stopping video...")
    os.system("sudo systemctl stop eyesypy")
    return "stopping video..."

@app.route('/start_video_engine')
def start_video_engine():
    print("starting video...")
    os.system("sudo systemctl start eyesypy")
    return "starting video..."

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

# --- live video stream ---------------------------------------------------
# The engine writes raw frames to /dev/shm, stream_encoder.py turns them into
# JPEG, and this hands them out as motion jpeg. Enable it with stream_enabled
# in the config, or from Video Settings on the instrument.

JPEG_CAPACITY = 512 * 1024
STREAM_BOUNDARY = "eyesyframe"


def open_jpeg_bus():
    try:
        return framebus.FrameBus(framebus.JPEG_PATH, JPEG_CAPACITY)
    except (OSError, ValueError):
        return None


@app.route('/live')
def live():
    return send_from_directory(app.static_folder, 'live.html')


@app.route('/stream_status')
def stream_status():
    bus = open_jpeg_bus()
    if bus is None:
        return jsonify(running=False)
    frame = bus.read()
    bus.close()
    if frame is None:
        return jsonify(running=False)
    return jsonify(running=True, width=frame[1], height=frame[2])


@app.route('/stream.mjpg')
def stream_mjpg():

    def frames():
        bus = None
        last_seq = 0
        # when the engine restarts the stream it makes a new file, so an
        # mmap that stops advancing means it is time to reopen
        last_change = time.time()
        try:
            while True:
                if bus is None:
                    bus = open_jpeg_bus()
                    if bus is None:
                        # engine not streaming, check back rather than 404
                        time.sleep(1)
                        if time.time() - last_change > 60:
                            return
                        continue
                    last_seq = 0
                    last_change = time.time()

                frame = bus.read()

                if frame is None or frame[3] == last_seq:
                    if time.time() - last_change > 3:
                        bus.close()
                        bus = None
                        continue
                    time.sleep(0.01)
                    continue

                payload, _, _, last_seq = frame
                last_change = time.time()
                yield (b"--" + STREAM_BOUNDARY.encode() + b"\r\n"
                       b"Content-Type: image/jpeg\r\n"
                       b"Content-Length: " + str(len(payload)).encode()
                       + b"\r\n\r\n" + payload + b"\r\n")
        except GeneratorExit:
            pass
        finally:
            if bus is not None:
                bus.close()

    return Response(
        frames(),
        mimetype=f"multipart/x-mixed-replace; boundary={STREAM_BOUNDARY}",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate",
                 "Pragma": "no-cache",
                 "Connection": "close"})

@app.route('/reload_mode', methods=['GET', 'POST'])
def reload_mode():
    mode = request.form.get('name')
    liblo.send(osc_target, "/set", mode)
    #liblo.send(osc_target, "/reload", 1)
    return "reloaded mode"

@app.route('/get_file', methods=['GET'])
def get_file():
    fpath = request.args.get('fpath')
    file_path = os.path.join("/", fpath)

    # Guess the MIME type of the file
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        mime_type = 'application/octet-stream'  # Default MIME type

    return send_file(file_path, mimetype=mime_type)

@app.route('/download')
def download():
    fpath = request.args.get('fpath')
    src = os.path.join(file_operations.BASE_DIR, urllib.parse.unquote(fpath))
    fname = os.path.basename(src)
    fname = urllib.parse.quote(fname)
    return send_file(src, mimetype='application/octet-stream', as_attachment=True, download_name=fname)

@app.route('/upload', methods=['POST'])
def upload():
    upload = request.files['files[]']
    dst = request.form['dst']
    folder = dst
    filename = werkzeug.utils.secure_filename(upload.filename)
    size = 0
    filepath = os.path.join(file_operations.BASE_DIR, folder, filename)
    filepath = file_operations.check_and_inc_name(filepath)  # As per your function

    with open(filepath, 'wb') as newfile:
        data = upload.read()
        size += len(data)
        newfile.write(data)

    print(f"Saved file, size: {size}")

    response = {
        "files": [
            {
                "name": "x",
                "size": size,
                "url": "na",
                "thumbnailUrl": "na",
                "deleteUrl": "na",
                "deleteType": "DELETE"
            }
        ]
    }
    return jsonify(response)

@app.route('/save', methods=['POST'])
def save():
    fpath = request.form.get('fpath')
    content = request.form.get('content')
    
    if not fpath or not content:
        return "Missing 'fpath' or 'content' in form data.", 400
    
    mode_path = "/" + fpath
    with open(mode_path, "w") as text_file:
        text_file.write(content)
    
    print("SAVED " + fpath)
    return "SAVED " + fpath

@app.route('/fmdata', methods=['GET', 'POST'])
def fmdata():

    data = request.args if request.method == 'GET' else request.get_json()

    if 'operation' in data:
        if data['operation'] == 'get_node':
            return jsonify(file_operations.get_node(data['path']))
        elif data['operation'] == 'create_node':
            return jsonify(file_operations.create(data['path'], data['name']))
        elif data['operation'] == 'rename_node':
            return jsonify(file_operations.rename(data['path'], data['name']))
        elif data['operation'] == 'delete_node':
            return jsonify(file_operations.delete(data['path']))
        elif data['operation'] == 'move_node':
            return jsonify(file_operations.move(data['src'], data['dst']))
        elif data['operation'] == 'copy_node':
            return jsonify(file_operations.copy(data['src'], data['dst']))
        elif data['operation'] == 'unzip_node':
            return jsonify(file_operations.unzip(data['path']))
        elif data['operation'] == 'download_node':
            return jsonify(file_operations.download(data['path']))
        elif data['operation'] == 'zip_node':
            return jsonify(file_operations.zip(data['path']))
    else:
        response = make_response(jsonify(message="No operation specified"), 400)
        response.headers['Content-Type'] = "application/json"
        return response

#@socketio.on('connect', namespace='/test')
#def test_connect():
#    sid = request.sid
#    socketio.start_background_task(target=background_thread, sid=sid)

#if __name__ == '__main__':
#    socketio.run(app, host='0.0.0.0', debug=True, port=8080)

@sock.route('/log_stream')
def log_stream(ws):
    background_thread(ws)  # Start sending logs to the WebSocket client

if __name__ == '__main__':
    # threaded so a long lived /stream.mjpg client does not block the editor
    app.run(host='0.0.0.0', debug=False, port=8080, threaded=True)




