// Shared definition of per-job options, used by both the main UI and the admin page.
window.CHEEZY_OPTIONS = [
  { group: "General", fields: [
    { key: "mode", label: "Mode", type: "select", choices: "mode",
      help: "copy = lossless remux (fast). transcode = re-encode (scrubs codec-level data too)." },
    { key: "container", label: "Output container", type: "select", choices: "container" },
  ]},
  { group: "What to strip", fields: [
    { key: "strip_global", label: "Container metadata (title, date, GPS, device, comments)", type: "bool" },
    { key: "strip_streams", label: "Per-stream metadata (language, handler names)", type: "bool" },
    { key: "strip_chapters", label: "Chapters", type: "bool" },
    { key: "drop_data", label: "Data tracks (GPS/telemetry, timecode)", type: "bool" },
    { key: "drop_attachments", label: "Attachments & cover art", type: "bool" },
    { key: "drop_subtitles", label: "Subtitles", type: "bool" },
    { key: "bitexact", label: "Encoder/tool tags (bitexact)", type: "bool" },
    { key: "strip_sei", label: "Encoder info in H.264/HEVC bitstream (transcode)", type: "bool" },
    { key: "random_filename", label: "Random output filename", type: "bool" },
    { key: "faststart", label: "Web faststart (MP4/MOV)", type: "bool" },
  ]},
  { group: "Video (transcode)", transcodeOnly: true, fields: [
    { key: "video_codec", label: "Video codec", type: "select", choices: "video_codec" },
    { key: "crf", label: "Quality (CRF, lower = better)", type: "number", min: 0, max: 63 },
    { key: "preset", label: "Preset (x264/x265 name, SVT-AV1 0-13)", type: "text", list: "preset" },
    { key: "max_height", label: "Max height px (0 = keep)", type: "number", min: 0, max: 4320 },
    { key: "fps", label: "Frame rate (0 = keep)", type: "number", min: 0, max: 240 },
    { key: "pix_fmt", label: "Pixel format", type: "select", choices: "pix_fmt" },
  ]},
  { group: "Audio (transcode)", transcodeOnly: true, fields: [
    { key: "audio_codec", label: "Audio codec", type: "select", choices: "audio_codec" },
    { key: "audio_bitrate", label: "Audio bitrate", type: "text" },
    { key: "audio_channels", label: "Channels (0 = keep)", type: "number", min: 0, max: 8 },
  ]},
];

window.renderOptions = function (container, values, choices) {
  container.innerHTML = "";
  const dl = document.createElement("datalist");
  dl.id = "preset-list";
  (choices.preset || []).forEach(p => { const o = document.createElement("option"); o.value = p; dl.appendChild(o); });
  container.appendChild(dl);
  for (const g of window.CHEEZY_OPTIONS) {
    const fs = document.createElement("fieldset");
    if (g.transcodeOnly) fs.dataset.transcodeOnly = "1";
    fs.innerHTML = `<legend>${g.group}</legend>`;
    const grid = document.createElement("div");
    grid.className = "grid";
    for (const f of g.fields) {
      const wrap = document.createElement("div");
      const id = "opt-" + f.key;
      const v = values[f.key];
      if (f.type === "bool") {
        wrap.innerHTML = `<label class="check"><input type="checkbox" id="${id}" data-opt="${f.key}" data-kind="bool" ${v ? "checked" : ""}> ${f.label}</label>`;
      } else if (f.type === "select") {
        const opts = (choices[f.choices] || []).map(c => `<option value="${c}" ${c === v ? "selected" : ""}>${c}</option>`).join("");
        wrap.innerHTML = `<label for="${id}">${f.label}</label><select id="${id}" data-opt="${f.key}">${opts}</select>`;
      } else {
        const t = f.type === "number" ? "number" : "text";
        const extra = f.type === "number" ? `min="${f.min}" max="${f.max}"` : "";
        const list = f.list ? `list="preset-list"` : "";
        wrap.innerHTML = `<label for="${id}">${f.label}</label><input type="${t}" id="${id}" data-opt="${f.key}" ${extra} ${list} value="${v ?? ""}">`;
      }
      if (f.help) wrap.innerHTML += `<div class="muted small">${f.help}</div>`;
      grid.appendChild(wrap);
    }
    fs.appendChild(grid);
    container.appendChild(fs);
  }
  const sync = () => {
    const t = container.querySelector('[data-opt="mode"]').value === "transcode";
    container.querySelectorAll("[data-transcode-only]").forEach(el => el.classList.toggle("hidden", !t));
  };
  container.querySelector('[data-opt="mode"]').addEventListener("change", sync);
  sync();
};

window.readOptions = function (container) {
  const out = {};
  container.querySelectorAll("[data-opt]").forEach(el => {
    out[el.dataset.opt] = el.dataset.kind === "bool" ? el.checked
      : el.type === "number" ? Number(el.value || 0) : el.value;
  });
  return out;
};
