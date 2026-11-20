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
  { group: "Keep from the original", fields: [
    { key: "keep_date", label: "Recording date", type: "bool" },
    { key: "keep_location", label: "GPS location", type: "bool" },
    { key: "keep_device", label: "Camera / phone make & model", type: "bool" },
  ], help: "Everything else is still stripped. Values you type below override kept ones." },
  { group: "Camera / phone", id: "device", fields: [
    { key: "_device", label: "Preset", type: "device", wide: true },
    { key: "meta_make", label: "Make", type: "text", placeholder: "Apple" },
    { key: "meta_model", label: "Model", type: "text", placeholder: "iPhone 17 Pro Max" },
    { key: "meta_software", label: "OS / firmware version", type: "text", placeholder: "26.1" },
    { key: "meta_apple_keys", label: "Write Apple/QuickTime keys (iPhone style; also used by Photos apps for date & location)", type: "bool" },
    { key: "meta_android_keys", label: "Write Android keys (com.android.manufacturer / model / version)", type: "bool" },
  ]},
  { group: "Date & location", id: "loc", fields: [
    { key: "meta_date", label: "Recording date & time (your local time)", type: "datetime" },
    { key: "meta_lat", label: "Latitude", type: "coord", placeholder: "48.8584" },
    { key: "meta_lon", label: "Longitude", type: "coord", placeholder: "2.2945" },
    { key: "meta_alt", label: "Altitude m (optional)", type: "coord", placeholder: "35" },
    { key: "_loc", label: "", type: "locationtools", wide: true },
  ]},
  { group: "Text tags", fields: [
    { key: "meta_title", label: "Title", type: "text" },
    { key: "meta_artist", label: "Artist / author", type: "text" },
    { key: "meta_copyright", label: "Copyright", type: "text" },
    { key: "meta_genre", label: "Genre", type: "text" },
    { key: "meta_comment", label: "Comment", type: "textarea", wide: true },
    { key: "meta_description", label: "Description", type: "textarea", wide: true },
    { key: "meta_custom", label: "Extra tags (one key=value per line)", type: "textarea", wide: true,
      placeholder: "album=Summer trip\ncom.apple.quicktime.location.name=Paris" },
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

(function () {
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pad = n => String(n).padStart(2, "0");
  // UTC ISO string -> value for <input type=datetime-local> (browser local time)
  const toLocalInput = iso => {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d)) return "";
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  };

  function deviceSelect() {
    const groups = (window.CHEEZY_DEVICES || []).map((g, gi) =>
      `<optgroup label="${esc(g.group)}">${g.items.map((d, di) => `<option value="${gi}:${di}">${esc(d.label)}</option>`).join("")}</optgroup>`).join("");
    return `<label for="opt-device">Preset</label>
      <select id="opt-device"><option value="">Custom / keep fields as they are</option><option value="clear">— None (clear device tags) —</option>${groups}</select>
      <div class="muted small">Fills in make, model and version the way that device writes them. You can still edit the fields.</div>`;
  }

  function locationTools() {
    return `<div class="row">
        <button type="button" class="secondary" data-loc="here">📍 Use my location</button>
        <button type="button" class="secondary" data-loc="map">🗺️ Pick on map</button>
        <button type="button" class="secondary" data-loc="clear">Clear</button>
        <span class="muted small" data-loc-status></span>
      </div>
      <div data-loc-map class="hidden" style="height:300px;border-radius:10px;margin-top:10px;border:1px solid var(--border)"></div>`;
  }

  function field(f, v) {
    const id = "opt-" + f.key;
    const ph = f.placeholder ? `placeholder="${esc(f.placeholder)}"` : "";
    switch (f.type) {
      case "bool":
        return `<label class="check"><input type="checkbox" id="${id}" data-opt="${f.key}" data-kind="bool" ${v ? "checked" : ""}> ${esc(f.label)}</label>`;
      case "select":
        return `<label for="${id}">${esc(f.label)}</label><select id="${id}" data-opt="${f.key}">${
          (this.choices[f.choices] || []).map(c => `<option value="${esc(c)}" ${c === v ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>`;
      case "textarea":
        return `<label for="${id}">${esc(f.label)}</label><textarea id="${id}" data-opt="${f.key}" rows="2" ${ph}>${esc(v)}</textarea>`;
      case "datetime":
        return `<label for="${id}">${esc(f.label)}</label><input type="datetime-local" step="1" id="${id}" data-opt="${f.key}" data-kind="datetime" value="${esc(toLocalInput(v))}">`;
      case "coord":
        return `<label for="${id}">${esc(f.label)}</label><input type="text" inputmode="decimal" id="${id}" data-opt="${f.key}" ${ph} value="${esc(v)}">`;
      case "number":
        return `<label for="${id}">${esc(f.label)}</label><input type="number" id="${id}" data-opt="${f.key}" min="${f.min}" max="${f.max}" value="${esc(v)}">`;
      case "device": return deviceSelect();
      case "locationtools": return locationTools();
      default:
        return `<label for="${id}">${esc(f.label)}</label><input type="text" id="${id}" data-opt="${f.key}" ${f.list ? 'list="preset-list"' : ""} ${ph} value="${esc(v)}">`;
    }
  }

  window.renderOptions = function (container, values, choices) {
    container.innerHTML = `<datalist id="preset-list">${(choices.preset || []).map(p => `<option value="${esc(p)}">`).join("")}</datalist>`;
    for (const g of window.CHEEZY_OPTIONS) {
      const fs = document.createElement("fieldset");
      if (g.transcodeOnly) fs.dataset.transcodeOnly = "1";
      const cells = g.fields.map(f =>
        `<div ${f.wide ? 'style="grid-column:1/-1"' : ""}>${field.call({ choices }, f, values[f.key])}${f.help ? `<div class="muted small">${esc(f.help)}</div>` : ""}</div>`).join("");
      fs.innerHTML = `<legend>${esc(g.group)}</legend>${g.help ? `<div class="muted small" style="margin-bottom:8px">${esc(g.help)}</div>` : ""}<div class="grid">${cells}</div>`;
      container.appendChild(fs);
    }
    wire(container);
  };

  function wire(c) {
    const q = k => c.querySelector(`[data-opt="${k}"]`);
    // transcode-only groups
    const sync = () => {
      const t = q("mode").value === "transcode";
      c.querySelectorAll("[data-transcode-only]").forEach(el => el.classList.toggle("hidden", !t));
    };
    q("mode").addEventListener("change", sync);
    sync();

    // device presets
    const dev = c.querySelector("#opt-device");
    const match = (window.CHEEZY_DEVICES || []).flatMap((g, gi) => g.items.map((d, di) => ({ d, v: `${gi}:${di}` })))
      .find(x => x.d.make === q("meta_make").value && x.d.model === q("meta_model").value);
    if (match) dev.value = match.v;
    dev.addEventListener("change", () => {
      if (dev.value === "") return;
      if (dev.value === "clear") {
        ["meta_make", "meta_model", "meta_software"].forEach(k => q(k).value = "");
        return;
      }
      const [gi, di] = dev.value.split(":").map(Number);
      const d = window.CHEEZY_DEVICES[gi].items[di];
      q("meta_make").value = d.make;
      q("meta_model").value = d.model;
      q("meta_software").value = d.software || "";
      q("meta_apple_keys").checked = d.style === "apple";
      q("meta_android_keys").checked = d.style === "android";
      // Device tags only survive if we don't also "keep" the original ones
      q("keep_device").checked = false;
    });
    ["meta_make", "meta_model"].forEach(k => q(k).addEventListener("input", () => { dev.value = ""; }));

    // location tools
    const status = c.querySelector("[data-loc-status]");
    const mapEl = c.querySelector("[data-loc-map]");
    let map = null, marker = null;
    const setLoc = (lat, lon, alt) => {
      q("meta_lat").value = (+lat).toFixed(6);
      q("meta_lon").value = (+lon).toFixed(6);
      if (alt != null && !isNaN(alt)) q("meta_alt").value = Math.round(alt);
      q("keep_location").checked = false;
      if (map) placeMarker(+lat, +lon);
    };
    const placeMarker = (lat, lon) => {
      if (marker) marker.setLatLng([lat, lon]); else marker = L.marker([lat, lon]).addTo(map);
    };
    c.querySelector('[data-loc="here"]').onclick = () => {
      if (!navigator.geolocation) { status.textContent = "Geolocation not available"; return; }
      status.textContent = "Locating…";
      navigator.geolocation.getCurrentPosition(
        p => { setLoc(p.coords.latitude, p.coords.longitude, p.coords.altitude); status.textContent = "Set from your device"; if (map) map.setView([p.coords.latitude, p.coords.longitude], 14); },
        e => { status.textContent = "Couldn't get location: " + e.message; },
        { enableHighAccuracy: true, timeout: 15000 });
    };
    c.querySelector('[data-loc="clear"]').onclick = () => {
      ["meta_lat", "meta_lon", "meta_alt"].forEach(k => q(k).value = "");
      if (marker) { marker.remove(); marker = null; }
      status.textContent = "";
    };
    c.querySelector('[data-loc="map"]').onclick = async () => {
      mapEl.classList.toggle("hidden");
      if (map || mapEl.classList.contains("hidden")) { map && map.invalidateSize(); return; }
      status.textContent = "Loading map…";
      try { await loadLeaflet(); } catch { status.textContent = "Couldn't load the map library"; return; }
      status.textContent = "Click the map to set the location";
      const lat = parseFloat(q("meta_lat").value), lon = parseFloat(q("meta_lon").value);
      const has = !isNaN(lat) && !isNaN(lon);
      map = L.map(mapEl).setView(has ? [lat, lon] : [20, 0], has ? 13 : 2);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        { maxZoom: 19, attribution: "© OpenStreetMap contributors" }).addTo(map);
      if (has) placeMarker(lat, lon);
      map.on("click", e => setLoc(e.latlng.lat, e.latlng.lng));
    };
  }

  let leafletPromise = null;
  function loadLeaflet() {
    if (window.L) return Promise.resolve();
    if (leafletPromise) return leafletPromise;
    leafletPromise = new Promise((res, rej) => {
      const css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = "/static/vendor/leaflet/leaflet.css";
      document.head.appendChild(css);
      const js = document.createElement("script");
      js.src = "/static/vendor/leaflet/leaflet.js";
      js.onload = res;
      js.onerror = () => { leafletPromise = null; rej(); };
      document.head.appendChild(js);
    });
    return leafletPromise;
  }

  window.readOptions = function (container) {
    const out = {};
    container.querySelectorAll("[data-opt]").forEach(el => {
      const k = el.dataset.opt;
      if (el.dataset.kind === "bool") out[k] = el.checked;
      else if (el.dataset.kind === "datetime") out[k] = el.value ? new Date(el.value).toISOString() : "";
      else if (el.type === "number") out[k] = Number(el.value || 0);
      else out[k] = el.value;
    });
    return out;
  };
})();
