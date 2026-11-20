# 🧀 CheezyTranscoder

A self-hosted web service that strips **all metadata** from video files: GPS/location, device make/model, creation dates, titles/artists/comments, chapters, telemetry/timecode tracks, cover art, and the encoder fingerprints that ffmpeg/x264/x265 normally leave behind.

It uses ffmpeg and FastAPI, ships as a single Dockerfile, and is made for [Coolify](https://coolify.io).

## Features
- **Web UI** with drag & drop, upload and processing progress, and a before/after metadata report
- **Fully customizable per job**: remux or re-encode, container, codec (H.264 / H.265 / VP9 / AV1), CRF, preset, max resolution, fps, pixel format, audio codec/bitrate/channels, and each kind of metadata separately
- **Admin settings UI** at `/settings`: public domain, site title, API key, CORS, limits, retention and default job options. Saved to `/data` and applied instantly with no restart.
- **Configurable domain**: used for download/share links and API examples, with optional strict Host enforcement
- **REST API**: synchronous `/strip`, or async jobs with progress. Interactive docs at `/api/docs`.
- Optional output filename randomization so the original filename doesn't leak
- Files are auto-deleted after a configurable retention time

## Deploy on Coolify
1. **+ New Resource → Public/Private Repository** and pick this repo.
2. Build Pack: **Dockerfile**. Ports Exposes: **8000**.
3. **Domains**: set your domain (e.g. `https://video.example.com`). The app picks it up automatically from `COOLIFY_URL`. You can also override it in `/settings`.
4. **Persistent Storage**: add a volume mounted at **`/data`** so settings survive redeploys.
5. (Recommended) Add the env var `ADMIN_PASSWORD`. If you don't, a password is generated and printed in the deployment logs on first boot.
6. Deploy, then open `https://your-domain/settings` and log in as user `admin`.

> Large uploads: Coolify's Traefik has no body-size limit by default. If Cloudflare proxies your domain, its free plan caps uploads at 100 MB.

## What gets removed
| Option | Removes | ffmpeg |
|---|---|---|
| Container metadata | title, artist, date, GPS `location`, Apple make/model, comments… | `-map_metadata -1` |
| Per-stream metadata | language, handler names, creation times | `-map_metadata:s -1` |
| Chapters | chapter markers/titles | `-map_chapters -1` |
| Data tracks | GPS/telemetry (GoPro, DJI), timecode tracks | drops `d` streams |
| Attachments & cover art | MKV attachments, embedded thumbnails | drops `t` streams + attached pics |
| Encoder/tool tags | `encoder=Lavf…` and version strings | `+bitexact`, plus a final remux pass |
| Bitstream encoder info | x264/x265 SEI blocks holding the full encoder version & settings | `filter_units` / `info=0` |

Container-structural fields (`major_brand`, `handler_name=VideoHandler`, `language=und`) are generic defaults written by the muxer, not data from your file.

## API
```bash
# One shot: upload and get the clean file back
curl -X POST https://video.example.com/strip \
  -H "X-API-Key: $API_KEY" \
  -F "file=@input.mp4" -OJ

# Re-encode to HEVC 1080p max
curl -X POST https://video.example.com/strip -F "file=@input.mov" \
  -F mode=transcode -F video_codec=libx265 -F crf=24 -F max_height=1080 -OJ

# Async job with progress
curl -X POST https://video.example.com/api/jobs -F "file=@input.mp4"   # -> {"id": "...", "status_url": ...}
curl https://video.example.com/api/jobs/<id>                            # status, progress, before/after
curl -OJ https://video.example.com/api/jobs/<id>/download
```

### Job options (form fields)
| Field | Values | Default |
|---|---|---|
| `mode` | `copy` (lossless remux), `transcode` | `copy` |
| `container` | `same`, `mp4`, `mkv`, `mov`, `webm` | `same` |
| `strip_global`, `strip_streams`, `strip_chapters`, `drop_data`, `drop_attachments`, `bitexact`, `strip_sei`, `random_filename`, `faststart` | `true`/`false` | `true` |
| `drop_subtitles` | `true`/`false` | `false` |
| `video_codec` | `libx264`, `libx265`, `libvpx-vp9`, `libsvtav1`, `copy`, `none` | `libx264` |
| `crf` | 0–63 | `20` |
| `preset` | x264/x265: `ultrafast`…`veryslow`; SVT-AV1: `0`–`13` | `medium` |
| `max_height` | px, `0` = keep | `0` |
| `fps` | `0` = keep | `0` |
| `pix_fmt` | `yuv420p`, `yuv420p10le`, `yuv422p`, `yuv444p` | `yuv420p` |
| `audio_codec` | `aac`, `libopus`, `libmp3lame`, `flac`, `copy`, `none` | `aac` |
| `audio_bitrate` | e.g. `128k` | `192k` |
| `audio_channels` | `0` = keep | `0` |

Admins can change the defaults in `/settings`, or turn off "Let users change processing options" to force them.

### Endpoints
| Method | Path | |
|---|---|---|
| GET | `/` | Web UI |
| GET | `/settings` | Admin UI (Basic auth, user `admin`) |
| POST | `/strip` | Upload and return the cleaned file |
| POST | `/api/jobs` | Create an async job |
| GET | `/api/jobs/{id}` | Job status and progress |
| GET | `/api/jobs/{id}/download` | Download the result |
| DELETE | `/api/jobs/{id}` | Delete a job now |
| GET | `/api/config` | Public config |
| GET/PUT | `/api/admin/settings` | Read/update settings (Basic auth) |
| GET | `/health` | Health check |
| GET | `/api/docs` | OpenAPI docs |

## Environment variables
All are optional. Except `ADMIN_PASSWORD`, `DATA_DIR` and `PORT`, they only set initial defaults; values saved in `/settings` win. See [.env.example](.env.example).

| Var | Default |
|---|---|
| `ADMIN_PASSWORD` | generated, shown in logs |
| `PUBLIC_URL` | `COOLIFY_URL` / `COOLIFY_FQDN`, else auto from request |
| `ENFORCE_DOMAIN` | `false` |
| `CORS_ORIGINS` | _(none)_ |
| `SITE_TITLE` | `CheezyTranscoder` |
| `API_KEY` | _(none, open)_ |
| `ALLOW_USER_OPTIONS` | `true` |
| `MAX_UPLOAD_MB` | `2048` |
| `FFMPEG_TIMEOUT` | `3600` |
| `MAX_CONCURRENT_JOBS` | `2` |
| `RETENTION_MINUTES` | `60` |
| `DATA_DIR` | `/data` |
| `PORT` | `8000` |

## Run locally
```bash
docker build -t cheezytranscoder .
docker run -p 8000:8000 -v cheezy-data:/data -e ADMIN_PASSWORD=changeme cheezytranscoder
```
Or use `docker compose up`.

## Notes
- Job state is kept in memory, so run a single replica. Jobs in progress are lost on restart.
- Job IDs are 128-bit random tokens. Anyone with a download link can fetch that file until it expires.
