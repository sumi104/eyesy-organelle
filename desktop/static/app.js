// EYESY simulator front end.
//
// One poll drives everything on screen except the video, which is an <img>
// the browser keeps open against /stream.mjpg. Controls that the user is
// actively dragging are left alone by the poll, otherwise the slider fights
// the thumb under the finger.

const $ = (id) => document.getElementById(id);

const POLL_MS = 200;

// panel buttons, index is the k the engine expects. The second label is what
// the button does with SHIFT (key 2) held, which is how the instrument works.
const KEYS = [
  { k: 1,  label: "OSD",   shift: "MENU" },
  { k: 2,  label: "SHIFT", shift: "SHIFT" },
  { k: 3,  label: "CLEAR", shift: "CLEAR" },
  { k: 4,  label: "MODE ◀", shift: "FG ◀" },
  { k: 5,  label: "MODE ▶", shift: "FG ▶" },
  { k: 6,  label: "SCN ◀", shift: "BG ◀" },
  { k: 7,  label: "SCN ▶", shift: "BG ▶" },
  { k: 8,  label: "SAVE",  shift: "UPDATE" },
  { k: 9,  label: "GRAB",  shift: "SEQ ▶" },
  { k: 10, label: "TRIG",  shift: "SEQ ●" },
];

let state = null;
let dragging = null;      // which control the pointer owns right now
let filterText = "";
let editorDirty = false;
let editorMode = null;
let editorFile = "main.py";
let editorFollowsPlayback = true;
let ace_editor = null;

// ---- api ------------------------------------------------------------------

async function post(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return res.json().catch(() => ({}));
}

async function get(path) {
  const res = await fetch(path);
  return res.json().catch(() => ({}));
}

// ---- mode list ------------------------------------------------------------

function renderModeList() {
  if (!state) return;
  const list = $("mode-list");
  const needle = filterText.toLowerCase();

  // modes that failed to import are not in state.modes, and they are the ones
  // most worth having in reach — clicking one opens it in the editor instead
  // of asking the engine to play something that will not import
  const errors = state.mode_errors || {};
  const all = [...new Set([...state.modes, ...Object.keys(errors)])]
    .sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
  const names = all.filter((n) => n.toLowerCase().includes(needle));

  list.innerHTML = "";
  for (const name of names) {
    const broken = !!errors[name];
    const li = document.createElement("li");
    li.textContent = name;
    li.title = broken ? name + "\n\n" + errors[name] : name;
    if (name === state.mode && !broken) li.classList.add("active");
    if (broken) li.classList.add("broken");
    li.onclick = () => {
      if (broken) return openInEditor(name);
      editorFollowsPlayback = true;
      post("/api/mode", { name });
    };
    list.appendChild(li);
  }

  const brokenCount = Object.keys(errors).length;
  $("mode-count").textContent =
    `${state.modes.length} modes` + (brokenCount ? ` / ${brokenCount} 読込失敗` : "");
}

// ---- knobs ----------------------------------------------------------------

function buildKnobs() {
  const wrap = $("knobs");
  wrap.innerHTML = "";
  for (let i = 0; i < 5; i++) {
    const div = document.createElement("div");
    div.className = "knob";
    div.id = `knob-wrap-${i}`;
    div.innerHTML =
      `<label><span>Knob ${i + 1}</span><span class="val" id="knob-val-${i}">0.000</span></label>` +
      `<input type="range" min="0" max="1" step="0.001" id="knob-${i}">`;
    wrap.appendChild(div);

    const input = div.querySelector("input");
    input.addEventListener("pointerdown", () => { dragging = `knob-${i}`; });
    input.addEventListener("input", () => {
      $(`knob-val-${i}`).textContent = Number(input.value).toFixed(3);
      post("/api/knob", { index: i, value: Number(input.value) });
    });
  }
}

// ---- keys -----------------------------------------------------------------

function buildKeys() {
  const wrap = $("keys");
  wrap.innerHTML = "";
  for (const spec of KEYS) {
    const btn = document.createElement("button");
    btn.className = "key";
    btn.id = `key-${spec.k}`;
    btn.innerHTML = `<span class="lbl">${spec.label}</span><b>${spec.k === 10 ? 0 : spec.k}</b>`;
    btn.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      btn.setPointerCapture(e.pointerId);
      post("/api/key", { k: spec.k, v: 1 });
    });
    const up = () => post("/api/key", { k: spec.k, v: 0 });
    btn.addEventListener("pointerup", up);
    btn.addEventListener("pointercancel", up);
    wrap.appendChild(btn);
  }
}

function updateKeyLabels(shift) {
  for (const spec of KEYS) {
    const btn = $(`key-${spec.k}`);
    if (!btn) continue;
    btn.querySelector(".lbl").textContent = shift ? spec.shift : spec.label;
  }
}

// the number row does the same thing, so a mode can be driven without aiming
// at buttons. Ignored while typing anywhere.
const heldKeys = new Set();

function keyForEvent(e) {
  if (e.metaKey || e.ctrlKey || e.altKey) return null;
  const t = e.target;
  if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" ||
            t.tagName === "SELECT" || t.isContentEditable)) return null;
  if (e.code === "Digit0") return 10;
  const m = /^Digit([1-9])$/.exec(e.code);
  return m ? Number(m[1]) : null;
}

document.addEventListener("keydown", (e) => {
  const k = keyForEvent(e);
  if (k === null || heldKeys.has(k)) return;
  heldKeys.add(k);
  post("/api/key", { k, v: 1 });
});

document.addEventListener("keyup", (e) => {
  const k = keyForEvent(e);
  if (k === null || !heldKeys.has(k)) return;
  heldKeys.delete(k);
  post("/api/key", { k, v: 0 });
});

// ---- status ---------------------------------------------------------------

const FLAGS = [
  ["auto_clear", "AUTO CLEAR"],
  ["osd", "OSD"],
  ["menu", "MENU"],
  ["freeze", "FREEZE"],
  ["audio_muted", "MUTE"],
  ["shift", "SHIFT"],
];

function renderStatus() {
  $("stat-fps").textContent = `${state.fps.toFixed(1)} fps`;
  $("stat-res").textContent = `${state.res[0]}×${state.res[1]}`;
  // the render loop only pays publish; encode happens on a worker thread
  $("stat-encode").textContent =
    `pub ${state.stream.publish_ms.toFixed(1)}ms / enc ${state.stream.encode_ms.toFixed(1)}ms`;
  $("modes-path").textContent = state.modes_path;

  const flags = $("flags");
  flags.innerHTML = "";
  for (const [key, label] of FLAGS) {
    const span = document.createElement("span");
    span.className = "flag" + (state.flags[key] ? " on" : "");
    span.textContent = label;
    flags.appendChild(span);
  }
  const pal = document.createElement("span");
  pal.className = "flag";
  pal.textContent = `FG ${state.palette.fg} / BG ${state.palette.bg}`;
  flags.appendChild(pal);

  const err = state.error || state.mode_errors[state.mode] || "";
  $("error").textContent = err;

  for (let i = 0; i < 5; i++) {
    const input = $(`knob-${i}`);
    if (dragging !== `knob-${i}`) {
      input.value = state.knobs[i];
      $(`knob-val-${i}`).textContent = state.knobs[i].toFixed(3);
    }
    $(`knob-wrap-${i}`).classList.toggle("override", !!state.knob_override[i]);
  }

  updateKeyLabels(state.flags.shift);
  $("key-3").classList.toggle("on", state.flags.auto_clear);
  $("key-1").classList.toggle("on", state.flags.osd || state.flags.menu);

  const a = state.audio;
  $("audio-error").textContent = a.error || (a.running ? "" : "入力が開けていません");
  if (dragging !== "gain") {
    $("gain").value = a.gain;
    $("gain-value").textContent = Number(a.gain).toFixed(2);
  }
  setMeter("peak-l", a.peak);
  setMeter("peak-r", a.peak_r);

  if (document.activeElement !== $("trigger-source"))
    $("trigger-source").value = String(a.trigger_source);

  // the engine is the authority on these, so a select the browser restored
  // from a previous session gets corrected rather than pushed back at it
  syncSelect("stream-width", state.stream.width);
  syncSelect("stream-fps", state.stream.fps);
  if (document.activeElement !== $("stream-smooth"))
    $("stream-smooth").checked = state.stream.smooth;
}

function syncSelect(id, value) {
  const el = $(id);
  if (document.activeElement !== el && el.value !== String(value))
    el.value = String(value);
}

function setMeter(id, peak) {
  const pct = Math.max(0, Math.min(100, (peak / 32767) * 100));
  const el = $(id);
  el.style.width = pct + "%";
  el.classList.toggle("hot", peak > 20000);
}

// ---- polling --------------------------------------------------------------

let lastModes = "";
let lastErrors = "";

async function poll() {
  try {
    const next = await get("/api/state");
    if (!next || !next.modes) return;
    state = next;

    const modesKey = state.modes.join(" ") + "|" + state.mode;
    const errorsKey = JSON.stringify(state.mode_errors);
    if (modesKey !== lastModes || errorsKey !== lastErrors) {
      lastModes = modesKey;
      lastErrors = errorsKey;
      renderModeList();
      maybeLoadEditor();
    }
    renderStatus();
  } catch (e) {
    // the engine is probably restarting, the next tick will pick it up
  }
}

// ---- audio + stream settings ---------------------------------------------

async function loadAudioDevices() {
  const data = await get("/api/audio/devices");
  const sel = $("audio-device");
  sel.innerHTML = "";
  for (const d of data.devices || []) {
    const opt = document.createElement("option");
    opt.value = d.index;
    opt.textContent = `${d.name} (${d.channels}ch ${d.samplerate}Hz)`;
    if (d.index === data.current) opt.selected = true;
    sel.appendChild(opt);
  }
}

$("audio-device").onchange = async (e) => {
  const res = await post("/api/audio/device", { index: Number(e.target.value) });
  if (!res.ok) $("audio-error").textContent = res.error || "開けませんでした";
};

$("gain").addEventListener("pointerdown", () => { dragging = "gain"; });
$("gain").addEventListener("input", (e) => {
  $("gain-value").textContent = Number(e.target.value).toFixed(2);
  post("/api/gain", { value: Number(e.target.value) });
});

$("trigger-source").onchange = (e) =>
  post("/api/trigger_source", { value: Number(e.target.value) });

function streamChanged() {
  const next = {
    width: Number($("stream-width").value),
    fps: Number($("stream-fps").value),
    smooth: $("stream-smooth").checked,
  };
  // ignore the change event a browser fires when it restores form values on
  // reload, which would otherwise quietly overwrite the saved settings
  if (state && state.stream && next.width === state.stream.width &&
      next.fps === state.stream.fps && next.smooth === state.stream.smooth)
    return;
  post("/api/stream", next);
}

$("stream-width").onchange = streamChanged;
$("stream-fps").onchange = streamChanged;
$("stream-smooth").onchange = streamChanged;

// ---- modes folder ---------------------------------------------------------

$("choose-folder").onclick = async () => {
  const res = await post("/api/choose_folder");
  if (res.ok) {
    lastModes = "";
    editorDirty = false;
    editorMode = null;
  }
};

$("rescan").onclick = async () => {
  await post("/api/rescan");
  lastModes = "";
};

$("mode-filter").oninput = (e) => {
  filterText = e.target.value;
  renderModeList();
};

// ---- editor ---------------------------------------------------------------

function initEditor() {
  ace_editor = ace.edit("editor");
  ace_editor.setTheme("ace/theme/monokai");
  ace_editor.session.setMode("ace/mode/python");
  ace_editor.setOptions({
    fontSize: 13,
    showPrintMargin: false,
    useSoftTabs: true,
    tabSize: 4,
    scrollPastEnd: 0.5,
  });
  ace_editor.on("change", () => {
    if (!editorDirty) {
      editorDirty = true;
      setEditorStatus("未保存の変更あり", "bad");
    }
  });
  ace_editor.commands.addCommand({
    name: "save",
    bindKey: { mac: "Cmd-S", win: "Ctrl-S" },
    exec: saveSource,
  });
}

function setEditorStatus(text, cls) {
  const el = $("editor-status");
  el.textContent = text;
  el.className = cls || "";
}

async function loadSource(mode, file) {
  const res = await get(
    `/api/source?mode=${encodeURIComponent(mode)}&file=${encodeURIComponent(file)}`);
  if (!res.ok) {
    setEditorStatus(res.error || "読み込めません", "bad");
    return;
  }
  editorMode = mode;
  editorFile = file;
  ace_editor.setValue(res.content, -1);
  editorDirty = false;
  $("editor-title").textContent = mode;
  setEditorStatus(`${mode}/${file}`, "");

  const files = await get(`/api/files?mode=${encodeURIComponent(mode)}`);
  const sel = $("editor-file");
  sel.innerHTML = "";
  for (const name of files.files || ["main.py"]) {
    const opt = document.createElement("option");
    opt.value = opt.textContent = name;
    if (name === file) opt.selected = true;
    sel.appendChild(opt);
  }
}

// follow the selected mode, unless there is unsaved work to lose or the
// editor was pointed at a mode that does not play
function maybeLoadEditor() {
  if (!document.body.classList.contains("editing")) return;
  if (!editorFollowsPlayback) return;
  if (!state || !state.mode) return;
  if (state.mode === editorMode) return;
  if (editorDirty) {
    setEditorStatus(
      `未保存のため ${editorMode} を開いたままです（保存するか破棄してください）`, "bad");
    return;
  }
  loadSource(state.mode, "main.py");
}

// a mode that fails to import cannot be played, so the list opens it here —
// fix it, save, and reload puts it back in the rotation
function openInEditor(name) {
  if (editorDirty && !confirm("未保存の変更を破棄しますか？")) return;
  editorDirty = false;
  editorFollowsPlayback = false;
  document.body.classList.add("editing");
  if (!ace_editor) initEditor();
  ace_editor.resize();
  loadSource(name, "main.py");
}

async function saveSource() {
  if (!editorMode) return;
  setEditorStatus("保存中…", "");
  const res = await post("/api/source", {
    mode: editorMode,
    file: editorFile,
    content: ace_editor.getValue(),
    reload: true,
  });
  if (res.ok) {
    editorDirty = false;
    // a mode that was broken is now the one playing, so let the editor track
    // the selection again
    editorFollowsPlayback = true;
    const at = new Date().toLocaleTimeString();
    setEditorStatus(`保存して再読込 ${at}`, "good");
  } else {
    setEditorStatus(res.error || "保存できませんでした", "bad");
  }
}

$("save").onclick = saveSource;

$("editor-file").onchange = (e) => {
  if (editorDirty && !confirm("未保存の変更を破棄しますか？")) {
    e.target.value = editorFile;
    return;
  }
  loadSource(editorMode, e.target.value);
};

$("editor-open").onclick = () => {
  document.body.classList.add("editing");
  editorFollowsPlayback = true;
  if (!ace_editor) initEditor();
  ace_editor.resize();
  maybeLoadEditor();
};

$("editor-toggle").onclick = () => {
  if (editorDirty && !confirm("未保存の変更を破棄しますか？")) return;
  editorDirty = false;
  document.body.classList.remove("editing");
};

document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "s") {
    e.preventDefault();
    if (document.body.classList.contains("editing")) saveSource();
  }
});

window.addEventListener("beforeunload", (e) => {
  if (editorDirty) e.preventDefault();
});

// ---- boot -----------------------------------------------------------------

document.addEventListener("pointerup", () => { dragging = null; });
document.addEventListener("pointercancel", () => { dragging = null; });

buildKnobs();
buildKeys();
loadAudioDevices();

// cache buster so a reload does not attach to a dead stream
$("screen").src = "/stream.mjpg?t=" + Date.now();

poll();
setInterval(poll, POLL_MS);
