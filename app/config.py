"""Persistent, UI-editable settings for CheezyTranscoder.

Settings live in DATA_DIR/settings.json (mount DATA_DIR as a volume in Coolify).
Environment variables provide the initial defaults; values saved through the
admin UI take precedence afterwards.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger("cheezy")

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
SETTINGS_FILE = DATA_DIR / "settings.json"
ADMIN_PW_FILE = DATA_DIR / "admin_password"


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


def _default_public_url() -> str:
    # PUBLIC_URL wins; otherwise use what Coolify injects for the app's domain.
    url = os.environ.get("PUBLIC_URL") or os.environ.get("COOLIFY_URL") or ""
    if not url and os.environ.get("COOLIFY_FQDN"):
        url = "https://" + os.environ["COOLIFY_FQDN"]
    # Coolify may pass a comma-separated list; take the first.
    return url.split(",")[0].strip().rstrip("/")


# Default per-job processing options (also editable in the admin UI).
DEFAULT_JOB_OPTIONS: dict[str, Any] = {
    "mode": "copy",              # copy | transcode
    "container": "same",         # same | mp4 | mkv | mov | webm
    # --- what to strip ---
    "strip_global": True,
    "strip_streams": True,
    "strip_chapters": True,
    "drop_data": True,
    "drop_attachments": True,
    "drop_subtitles": False,
    "bitexact": True,
    "strip_sei": True,           # remove encoder-info SEI units from H.264/HEVC bitstream
    "random_filename": True,
    "faststart": True,
    # --- transcode: video ---
    "video_codec": "libx264",    # libx264 | libx265 | libvpx-vp9 | libsvtav1 | copy | none
    "crf": 20,
    "preset": "medium",
    "max_height": 0,             # 0 = keep
    "fps": 0,                    # 0 = keep
    "pix_fmt": "yuv420p",
    # --- transcode: audio ---
    "audio_codec": "aac",        # aac | libopus | libmp3lame | flac | copy | none
    "audio_bitrate": "192k",
    "audio_channels": 0,         # 0 = keep
    # --- custom metadata written AFTER stripping (empty = don't write) ---
    "meta_title": "",
    "meta_artist": "",
    "meta_comment": "",
    "meta_description": "",
    "meta_copyright": "",
    "meta_genre": "",
    "meta_date": "",             # ISO 8601, e.g. 2023-07-04T12:30:00Z
    "meta_lat": "",              # decimal degrees
    "meta_lon": "",
    "meta_alt": "",              # metres (optional)
    "meta_make": "",
    "meta_model": "",
    "meta_software": "",
    "meta_custom": "",           # extra "key=value" lines
    "meta_apple_keys": True,     # also write com.apple.quicktime.* keys (MP4/MOV)
    "meta_android_keys": False,  # also write com.android.manufacturer/model/version
    # --- keep selected original values instead of stripping them ---
    "keep_date": False,
    "keep_location": False,
    "keep_device": False,
}


def _defaults() -> dict[str, Any]:
    return {
        "site_title": os.environ.get("SITE_TITLE", "CheezyTranscoder"),
        "public_url": _default_public_url(),
        "enforce_domain": _env_bool("ENFORCE_DOMAIN", False),
        "cors_origins": os.environ.get("CORS_ORIGINS", ""),
        "api_key": os.environ.get("API_KEY", ""),
        "max_upload_mb": int(os.environ.get("MAX_UPLOAD_MB", "2048")),
        "ffmpeg_timeout": int(os.environ.get("FFMPEG_TIMEOUT", "3600")),
        "max_concurrent_jobs": int(os.environ.get("MAX_CONCURRENT_JOBS", "2")),
        "retention_minutes": int(os.environ.get("RETENTION_MINUTES", "60")),
        "allow_user_options": _env_bool("ALLOW_USER_OPTIONS", True),
        "job_defaults": dict(DEFAULT_JOB_OPTIONS),
    }


class Settings:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data = _defaults()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if SETTINGS_FILE.exists():
            try:
                saved = json.loads(SETTINGS_FILE.read_text())
                jd = {**self._data["job_defaults"], **saved.pop("job_defaults", {})}
                self._data.update({k: v for k, v in saved.items() if k in self._data})
                self._data["job_defaults"] = jd
            except Exception as e:  # corrupt file -> keep defaults
                log.warning("Could not read %s: %s", SETTINGS_FILE, e)
        self.admin_password = self._load_admin_password()

    def _load_admin_password(self) -> str:
        env = os.environ.get("ADMIN_PASSWORD", "").strip()
        if env:
            return env
        if ADMIN_PW_FILE.exists():
            return ADMIN_PW_FILE.read_text().strip()
        pw = secrets.token_urlsafe(18)
        ADMIN_PW_FILE.write_text(pw)
        try:
            ADMIN_PW_FILE.chmod(0o600)
        except OSError:
            pass
        log.warning("=" * 60)
        log.warning("Generated admin password (user 'admin'): %s", pw)
        log.warning("Set ADMIN_PASSWORD env var to choose your own.")
        log.warning("=" * 60)
        return pw

    def get(self, key: str) -> Any:
        with self._lock:
            return self._data[key]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data))

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            for k, v in patch.items():
                if k == "job_defaults" and isinstance(v, dict):
                    self._data["job_defaults"].update(
                        {jk: jv for jk, jv in v.items() if jk in DEFAULT_JOB_OPTIONS}
                    )
                elif k in self._data:
                    self._data[k] = v
            if isinstance(self._data.get("public_url"), str):
                self._data["public_url"] = self._data["public_url"].strip().rstrip("/")
            tmp = SETTINGS_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, indent=2))
            tmp.replace(SETTINGS_FILE)
            return json.loads(json.dumps(self._data))


settings = Settings()
