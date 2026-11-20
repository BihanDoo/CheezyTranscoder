"""Validation of job options and construction of the ffmpeg command line."""

from __future__ import annotations

import asyncio
import json
import re
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
    o.update({k: v for k, v in raw.items() if k in DEFAULT_JOB_OPTIONS and v not in (None, "")})

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
    return o


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

    # ---- codecs ----
    if o["mode"] == "copy":
        cmd += ["-c", "copy"]
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
            cmd += ["-c:s", "mov_text" if ext in MP4_LIKE else ("webvtt" if ext == ".webm" else "copy")]
        if not o["drop_data"]:
            cmd += ["-c:d", "copy"]

    if ext in MP4_LIKE and o["faststart"]:
        cmd += ["-movflags", "+faststart"]

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
