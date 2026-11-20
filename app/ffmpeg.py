"""Validation of job options and construction of the ffmpeg command line."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import DEFAULT_JOB_OPTIONS

VIDEO_CODECS = {"libx264", "libx265", "libvpx-vp9", "libsvtav1", "copy", "none"}
AUDIO_CODECS = {"aac", "libopus", "libmp3lame", "flac", "copy", "none"}
CONTAINERS = {"same", "mp4", "mkv", "mov", "webm"}
PIX_FMTS = {"yuv420p", "yuv420p10le", "yuv422p", "yuv444p"}
X26X_PRESETS = {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"}
BITRATE_RE = re.compile(r"^\d{2,4}k$")

INPUT_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".ts", ".mts", ".m2ts",
             ".flv", ".3gp", ".wmv", ".mpg", ".mpeg"}
MP4_LIKE = {".mp4", ".mov", ".m4v", ".3gp"}

BOOL_KEYS = {k for k, v in DEFAULT_JOB_OPTIONS.items() if isinstance(v, bool)}
META_KEYS = {k for k in DEFAULT_JOB_OPTIONS
             if k.startswith("meta_") and k not in ("meta_apple_keys", "meta_android_keys")}

# Simple text fields: option -> (generic tag, Apple QuickTime key)
META_TEXT = {
    "meta_title": ("title", "com.apple.quicktime.title"),
    "meta_artist": ("artist", "com.apple.quicktime.artist"),
    "meta_comment": ("comment", "com.apple.quicktime.comment"),
    "meta_description": ("description", "com.apple.quicktime.description"),
    "meta_copyright": ("copyright", "com.apple.quicktime.copyright"),
    "meta_genre": ("genre", "com.apple.quicktime.genre"),
    "meta_make": ("make", "com.apple.quicktime.make"),
    "meta_model": ("model", "com.apple.quicktime.model"),
    "meta_software": ("software", "com.apple.quicktime.software"),
}
TAG_KEY_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")
ISO6709_RE = re.compile(r"^([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)?")


class OptionError(ValueError):
    pass


def _bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _int(v: Any, lo: int, hi: int, name: str) -> int:
    try:
        i = int(v)
    except (TypeError, ValueError):
        raise OptionError(f"{name} must be an integer")
    if not lo <= i <= hi:
        raise OptionError(f"{name} must be between {lo} and {hi}")
    return i


def validate_options(raw: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """Merge raw user options over defaults and validate every value."""
    o = {**DEFAULT_JOB_OPTIONS, **defaults}
    o.update({k: v for k, v in raw.items()
              if k in DEFAULT_JOB_OPTIONS and v is not None and (v != "" or k in META_KEYS)})

    for k in BOOL_KEYS:
        o[k] = _bool(o[k])

    if o["mode"] not in ("copy", "transcode"):
        raise OptionError("mode must be 'copy' or 'transcode'")
    if o["container"] not in CONTAINERS:
        raise OptionError(f"container must be one of {sorted(CONTAINERS)}")
    if o["video_codec"] not in VIDEO_CODECS:
        raise OptionError(f"video_codec must be one of {sorted(VIDEO_CODECS)}")
    if o["audio_codec"] not in AUDIO_CODECS:
        raise OptionError(f"audio_codec must be one of {sorted(AUDIO_CODECS)}")
    if o["pix_fmt"] not in PIX_FMTS:
        raise OptionError(f"pix_fmt must be one of {sorted(PIX_FMTS)}")
    o["audio_bitrate"] = str(o["audio_bitrate"]).strip().lower()
    if not BITRATE_RE.match(o["audio_bitrate"]):
        raise OptionError("audio_bitrate must look like '192k'")
    o["crf"] = _int(o["crf"], 0, 63, "crf")
    o["max_height"] = _int(o["max_height"], 0, 4320, "max_height")
    o["fps"] = _int(o["fps"], 0, 240, "fps")
    o["audio_channels"] = _int(o["audio_channels"], 0, 8, "audio_channels")

    preset = str(o["preset"]).strip()
    if o["video_codec"] == "libsvtav1":
        if not preset.isdigit():
            preset = "8"
        preset = str(_int(preset, 0, 13, "preset (SVT-AV1 0-13)"))
    elif o["video_codec"] in ("libx264", "libx265"):
        if preset not in X26X_PRESETS:
            raise OptionError(f"preset must be one of {sorted(X26X_PRESETS)}")
    o["preset"] = preset

    if o["mode"] == "transcode" and o["video_codec"] == "none" and o["audio_codec"] == "none":
        raise OptionError("Can't drop both video and audio")
    _validate_meta(o)
    return o


def _clean_text(v: Any, name: str, limit: int = 1000) -> str:
    t = str(v or "").replace("\r\n", "\n").strip()
    t = "".join(c for c in t if c == "\n" or ord(c) >= 32)
    if len(t) > limit:
        raise OptionError(f"{name} is too long (max {limit} characters)")
    return t


def _float(v: Any, lo: float, hi: float, name: str) -> str:
    t = str(v or "").strip()
    if not t:
        return ""
    try:
        f = float(t)
    except ValueError:
        raise OptionError(f"{name} must be a number")
    if not lo <= f <= hi:
        raise OptionError(f"{name} must be between {lo} and {hi}")
    return repr(f)


def parse_date(v: str) -> datetime:
    t = v.strip()
    if re.fullmatch(r"\d{4}", t):
        t += "-01-01"
    try:
        d = datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        raise OptionError("meta_date must be ISO 8601, e.g. 2023-07-04T12:30:00Z")
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    if not 1904 <= d.year <= 2100:  # QuickTime epoch starts 1904
        raise OptionError("meta_date year must be between 1904 and 2100")
    return d.astimezone(timezone.utc)


def _validate_meta(o: dict[str, Any]) -> None:
    for k in META_TEXT:
        o[k] = _clean_text(o[k], k)
    o["meta_date"] = _clean_text(o["meta_date"], "meta_date", 40)
    if o["meta_date"]:
        o["meta_date"] = parse_date(o["meta_date"]).strftime("%Y-%m-%dT%H:%M:%SZ")
    o["meta_lat"] = _float(o["meta_lat"], -90, 90, "meta_lat (latitude)")
    o["meta_lon"] = _float(o["meta_lon"], -180, 180, "meta_lon (longitude)")
    o["meta_alt"] = _float(o["meta_alt"], -12000, 100000, "meta_alt (altitude)")
    if bool(o["meta_lat"]) != bool(o["meta_lon"]):
        raise OptionError("Set both latitude and longitude (or neither)")
    if o["meta_alt"] and not o["meta_lat"]:
        raise OptionError("Altitude needs latitude and longitude")
    custom = _clean_text(o["meta_custom"], "meta_custom", 5000)
    lines = []
    for line in custom.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, val = line.partition("=")
        key = key.strip()
        if not sep or not TAG_KEY_RE.match(key):
            raise OptionError(f"meta_custom: bad line '{line[:60]}' (use key=value, key: letters, digits, _ . : -)")
        lines.append(f"{key}={val.strip()}")
    if len(lines) > 50:
        raise OptionError("meta_custom: at most 50 tags")
    o["meta_custom"] = "\n".join(lines)


def iso6709(lat: str, lon: str, alt: str = "") -> str:
    out = f"{float(lat):+08.4f}{float(lon):+09.4f}"
    if alt:
        out += f"{float(alt):+08.3f}"
    return out + "/"


def apply_kept(o: dict[str, Any], before: dict[str, Any] | None) -> dict[str, Any]:
    """Fill empty custom fields with the ORIGINAL file's date/location/device if asked to."""
    if not before or not (o["keep_date"] or o["keep_location"] or o["keep_device"]):
        return o
    tags: dict[str, str] = {}
    for st in before.get("streams", []):  # stream tags first, container tags win
        for k, v in (st.get("tags") or {}).items():
            tags.setdefault(k.lower(), v)
    tags.update({k.lower(): v for k, v in (before.get("format_tags") or {}).items()})
    o = dict(o)
    if o["keep_date"] and not o["meta_date"]:
        for k in ("com.apple.quicktime.creationdate", "creation_time", "date"):
            if tags.get(k):
                try:
                    o["meta_date"] = parse_date(tags[k]).strftime("%Y-%m-%dT%H:%M:%SZ")
                    break
                except OptionError:
                    continue
    if o["keep_location"] and not o["meta_lat"]:
        for k in ("com.apple.quicktime.location.iso6709", "location", "location-eng"):
            m = ISO6709_RE.match(tags.get(k, ""))
            if m:
                o["meta_lat"], o["meta_lon"] = m.group(1), m.group(2)
                o["meta_alt"] = m.group(3) or ""
                break
    if o["keep_device"]:
        for opt, keys in (("meta_make", ("com.apple.quicktime.make", "com.android.manufacturer", "make")),
                          ("meta_model", ("com.apple.quicktime.model", "com.android.model", "model")),
                          ("meta_software", ("com.apple.quicktime.software", "com.android.version", "software"))):
            if not o[opt]:
                o[opt] = next((tags[k] for k in keys if tags.get(k)), "")
    return o


def metadata_pairs(o: dict[str, Any], ext: str) -> tuple[list[tuple[str, str]], bool]:
    """Tags to write after stripping, and whether QuickTime mdta keys are needed."""
    apple = o["meta_apple_keys"] and ext in MP4_LIKE
    pairs: list[tuple[str, str]] = []
    for opt, (generic, qt) in META_TEXT.items():
        if o[opt]:
            pairs.append((generic, o[opt]))
            if apple:
                pairs.append((qt, o[opt]))
    if o["meta_date"]:
        d = parse_date(o["meta_date"])
        pairs.append(("creation_time", d.strftime("%Y-%m-%dT%H:%M:%S.000000Z")))
        pairs.append(("date", d.strftime("%Y-%m-%d")))
        if apple:
            pairs.append(("com.apple.quicktime.creationdate", d.strftime("%Y-%m-%dT%H:%M:%S+0000")))
    if o["meta_lat"] and o["meta_lon"]:
        loc = iso6709(o["meta_lat"], o["meta_lon"], o["meta_alt"])
        pairs.append(("location", loc))
        if apple:
            pairs.append(("com.apple.quicktime.location.ISO6709", loc))
    android = o["meta_android_keys"]
    if android:
        # The keys Android's camera/MediaRecorder writes (Pixel, Samsung, ...)
        for opt, key in (("meta_make", "com.android.manufacturer"),
                         ("meta_model", "com.android.model"),
                         ("meta_software", "com.android.version")):
            if o[opt]:
                pairs.append((key, o[opt]))
    for line in o["meta_custom"].splitlines():
        k, _, v = line.partition("=")
        pairs.append((k, v))
    return pairs, (apple or android) and ext in MP4_LIKE and bool(pairs)


def output_ext(input_ext: str, o: dict[str, Any]) -> str:
    if o["container"] != "same":
        ext = "." + o["container"]
    elif o["mode"] == "transcode":
        ext = ".webm" if input_ext == ".webm" else (".mkv" if input_ext == ".mkv" else ".mp4")
    else:
        ext = input_ext
    # WebM only holds VP8/VP9/AV1 + Vorbis/Opus
    if ext == ".webm" and o["mode"] == "transcode" and (
        o["video_codec"] not in ("libvpx-vp9", "libsvtav1", "none")
        or o["audio_codec"] not in ("libopus", "none")
    ):
        ext = ".mkv"
    return ext


def build_cmd(src: Path, dst: Path, o: dict[str, Any]) -> list[str]:
    ext = dst.suffix.lower()
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", str(src)]

    # ---- stream selection ----
    want_v = not (o["mode"] == "transcode" and o["video_codec"] == "none")
    want_a = not (o["mode"] == "transcode" and o["audio_codec"] == "none")
    if want_v:
        # "V" (capital) = real video only, excluding embedded cover-art images
        cmd += ["-map", "0:V?" if o["drop_attachments"] else "0:v?"]
    if want_a:
        cmd += ["-map", "0:a?"]
    if not o["drop_subtitles"]:
        cmd += ["-map", "0:s?"]
    if not o["drop_data"]:
        cmd += ["-map", "0:d?"]
    if not o["drop_attachments"]:
        cmd += ["-map", "0:t?"]

    # ---- metadata stripping ----
    if o["strip_global"]:
        cmd += ["-map_metadata", "-1"]
    if o["strip_streams"]:
        cmd += ["-map_metadata:s", "-1"]
    if o["strip_chapters"]:
        cmd += ["-map_chapters", "-1"]
    if o["bitexact"]:
        cmd += ["-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact"]

    # ---- custom metadata (written after everything above was stripped) ----
    pairs, use_mdta = metadata_pairs(o, ext)
    for k, v in pairs:
        cmd += ["-metadata", f"{k}={v}"]

    # ---- codecs ----
    sub_codec = "mov_text" if ext in MP4_LIKE else ("webvtt" if ext == ".webm" else "srt")
    if o["mode"] == "copy":
        cmd += ["-c", "copy"]
        # Subtitle formats are container-specific: convert when the container changes
        if not o["drop_subtitles"] and src.suffix.lower() != ext:
            cmd += ["-c:s", sub_codec]
    else:
        vc = o["video_codec"]
        if want_v:
            if vc == "copy":
                cmd += ["-c:v", "copy"]
            else:
                cmd += ["-c:v", vc, "-pix_fmt", o["pix_fmt"]]
                if vc in ("libx264", "libx265"):
                    cmd += ["-preset", o["preset"], "-crf", str(o["crf"])]
                    if vc == "libx265":
                        # info=0 stops x265 writing its version/settings SEI
                        x265p = "log-level=error" + (":info=0" if o["strip_sei"] else "")
                        cmd += ["-tag:v", "hvc1", "-x265-params", x265p]
                    elif o["strip_sei"]:
                        # x264 writes an SEI NAL (type 6) with its version + full settings
                        cmd += ["-bsf:v", "filter_units=remove_types=6"]
                elif vc == "libvpx-vp9":
                    cmd += ["-crf", str(o["crf"]), "-b:v", "0", "-row-mt", "1"]
                elif vc == "libsvtav1":
                    cmd += ["-preset", o["preset"], "-crf", str(o["crf"])]
                filters = []
                if o["max_height"]:
                    h = o["max_height"]
                    filters.append(f"scale=-2:'min({h},ih)'")
                if o["fps"]:
                    filters.append(f"fps={o['fps']}")
                if filters:
                    cmd += ["-vf", ",".join(filters)]
        ac = o["audio_codec"]
        if want_a:
            if ac == "copy":
                cmd += ["-c:a", "copy"]
            else:
                cmd += ["-c:a", ac]
                if ac != "flac":
                    cmd += ["-b:a", o["audio_bitrate"]]
                if o["audio_channels"]:
                    cmd += ["-ac", str(o["audio_channels"])]
        if not o["drop_subtitles"]:
            cmd += ["-c:s", sub_codec]
        if not o["drop_data"]:
            cmd += ["-c:d", "copy"]

    movflags = []
    if ext in MP4_LIKE and o["faststart"]:
        movflags.append("+faststart")
    if use_mdta:
        movflags.append("+use_metadata_tags")
    if movflags:
        cmd += ["-movflags", "".join(movflags)]

    cmd += ["-progress", "pipe:1", "-nostats", str(dst)]
    return cmd


async def probe_duration(src: Path) -> float:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(src),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    try:
        return float(json.loads(out)["format"]["duration"])
    except Exception:
        return 0.0


async def probe_metadata(path: Path) -> dict[str, Any]:
    """Return format + stream tags and chapter count (used for before/after report)."""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-show_chapters",
        "-of", "json", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    try:
        data = json.loads(out)
    except Exception:
        return {}
    return {
        "format_tags": data.get("format", {}).get("tags", {}),
        "streams": [
            {"index": s.get("index"), "type": s.get("codec_type"), "codec": s.get("codec_name"),
             "tags": s.get("tags", {})}
            for s in data.get("streams", [])
        ],
        "chapters": len(data.get("chapters", [])),
    }


async def run(cmd: list[str], duration: float, timeout: int,
              on_progress: Callable[[float], None]) -> None:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stderr_chunks: list[bytes] = []

    async def read_stderr() -> None:
        assert proc.stderr
        while chunk := await proc.stderr.read(4096):
            stderr_chunks.append(chunk)
            if len(stderr_chunks) > 50:
                del stderr_chunks[:-50]

    async def read_progress() -> None:
        assert proc.stdout
        async for line in proc.stdout:
            k, _, v = line.decode(errors="replace").strip().partition("=")
            if k == "out_time_us" and duration > 0 and v.isdigit():
                on_progress(min(99.0, int(v) / 1e6 / duration * 100))

    try:
        await asyncio.wait_for(
            asyncio.gather(read_stderr(), read_progress(), proc.wait()), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError("Processing timed out")
    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        raise
    if proc.returncode != 0:
        tail = b"".join(stderr_chunks).decode(errors="replace")[-1500:]
        raise RuntimeError(f"ffmpeg failed: {tail}")
