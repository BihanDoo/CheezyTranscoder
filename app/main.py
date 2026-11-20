"""CheezyTranscoder - strips metadata from video files using ffmpeg."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import secrets
import shutil
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile

from . import ffmpeg
from .config import DEFAULT_JOB_OPTIONS, settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cheezy")

WORK_DIR = Path(os.environ.get("WORK_DIR", tempfile.gettempdir())) / "cheezy-jobs"
STATIC = Path(__file__).parent / "static"


# --------------------------------------------------------------------------- jobs
@dataclass
class Job:
    id: str
    original_name: str
    options: dict[str, Any]
    dir: Path
    status: str = "queued"          # queued | processing | done | error
    progress: float = 0.0
    error: str | None = None
    output: Path | None = None
    download_name: str | None = None
    created: float = field(default_factory=time.time)
    finished: float | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    task: asyncio.Task | None = None


JOBS: dict[str, Job] = {}


class Limiter:
    """Concurrency limiter whose limit is read live from settings."""

    def __init__(self) -> None:
        self.active = 0
        self.cond = asyncio.Condition()

    async def __aenter__(self) -> None:
        async with self.cond:
            await self.cond.wait_for(lambda: self.active < max(1, int(settings.get("max_concurrent_jobs"))))
            self.active += 1

    async def __aexit__(self, *exc: Any) -> None:
        async with self.cond:
            self.active -= 1
            self.cond.notify_all()


limiter = Limiter()


def public_base(request: Request) -> str:
    url = settings.get("public_url")
    return url if url else str(request.base_url).rstrip("/")


def job_view(job: Job, request: Request) -> dict[str, Any]:
    base = public_base(request)
    return {
        "id": job.id,
        "status": job.status,
        "progress": round(job.progress, 1),
        "error": job.error,
        "options": job.options,
        "created": job.created,
        "finished": job.finished,
        "expires": job.created + settings.get("retention_minutes") * 60,
        "status_url": f"{base}/api/jobs/{job.id}",
        "download_url": f"{base}/api/jobs/{job.id}/download" if job.status == "done" else None,
        "download_name": job.download_name,
        "before": job.before,
        "after": job.after,
    }


async def process(job: Job, src: Path) -> None:
    try:
        async with limiter:
            job.status = "processing"
            o = job.options
            ext = ffmpeg.output_ext(src.suffix.lower(), o)
            dst = job.dir / f"output{ext}"
            job.before = await ffmpeg.probe_metadata(src)
            duration = await ffmpeg.probe_duration(src)

            def prog(p: float) -> None:
                job.progress = p

            timeout = int(settings.get("ffmpeg_timeout"))
            if o["mode"] == "transcode":
                # Encoders always stamp an "encoder" tag; a final lossless remux removes it.
                stage = job.dir / f"stage{ext}"
                await ffmpeg.run(ffmpeg.build_cmd(src, stage, o), duration, timeout, prog)
                src.unlink(missing_ok=True)
                await ffmpeg.run(ffmpeg.build_cmd(stage, dst, {**o, "mode": "copy"}), 0, timeout, prog)
                stage.unlink(missing_ok=True)
            else:
                await ffmpeg.run(ffmpeg.build_cmd(src, dst, o), duration, timeout, prog)
            job.after = await ffmpeg.probe_metadata(dst)
            src.unlink(missing_ok=True)
            job.output = dst
            stem = Path(job.original_name).stem or "video"
            job.download_name = (f"video_{uuid.uuid4().hex[:8]}{ext}" if o["random_filename"]
                                 else f"{stem}_clean{ext}")
            job.progress = 100.0
            job.status = "done"
    except asyncio.CancelledError:
        job.status, job.error = "error", "Cancelled"
        raise
    except Exception as e:  # noqa: BLE001
        log.info("Job %s failed: %s", job.id, e)
        job.status, job.error = "error", str(e)
        src.unlink(missing_ok=True)
    finally:
        job.finished = time.time()


def delete_job(job_id: str) -> None:
    job = JOBS.pop(job_id, None)
    if job:
        if job.task and not job.task.done():
            job.task.cancel()
        shutil.rmtree(job.dir, ignore_errors=True)


async def janitor() -> None:
    while True:
        await asyncio.sleep(30)
        ttl = int(settings.get("retention_minutes")) * 60
        now = time.time()
        for jid, job in list(JOBS.items()):
            if job.status in ("done", "error") and now - (job.finished or job.created) > ttl:
                delete_job(jid)


@asynccontextmanager
async def lifespan(_: FastAPI):
    shutil.rmtree(WORK_DIR, ignore_errors=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    t = asyncio.create_task(janitor())
    pu = settings.get("public_url")
    log.info("CheezyTranscoder ready. Public URL: %s", pu or "(auto from request)")
    yield
    t.cancel()


app = FastAPI(title="CheezyTranscoder", version="2.0.0", lifespan=lifespan,
              docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# --------------------------------------------------------------------------- middleware
def _allowed_origins() -> list[str]:
    raw = settings.get("cors_origins") or ""
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    return origins


@app.middleware("http")
async def domain_cors_limits(request: Request, call_next):
    path = request.url.path

    # Enforce configured domain (health check & localhost always allowed)
    if settings.get("enforce_domain") and settings.get("public_url") and path != "/health":
        want = (urlparse(settings.get("public_url")).hostname or "").lower()
        host = (request.headers.get("host") or "").split(":")[0].lower()
        if host not in (want, "localhost", "127.0.0.1"):
            return JSONResponse({"detail": "Unknown host"}, status_code=421)

    # Early reject of oversize uploads
    if request.method == "POST" and path in ("/api/jobs", "/strip"):
        cl = request.headers.get("content-length")
        limit = int(settings.get("max_upload_mb")) * 1024 * 1024
        if cl and cl.isdigit() and int(cl) > limit + 1024 * 1024:
            return JSONResponse({"detail": f"File exceeds {settings.get('max_upload_mb')} MB"},
                                status_code=413)

    origin = request.headers.get("origin")
    allowed = _allowed_origins()
    cors_ok = origin and ("*" in allowed or origin.rstrip("/") in allowed)
    if request.method == "OPTIONS" and cors_ok:
        resp: Response = Response(status_code=204)
    else:
        resp = await call_next(request)
    if cors_ok:
        resp.headers["Access-Control-Allow-Origin"] = "*" if "*" in allowed else origin
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
        resp.headers["Access-Control-Expose-Headers"] = "Content-Disposition"
        resp.headers["Vary"] = "Origin"
    return resp


# --------------------------------------------------------------------------- auth
def check_api_key(request: Request) -> None:
    key = settings.get("api_key")
    if not key:
        return
    sent = request.headers.get("x-api-key") or request.query_params.get("api_key") or ""
    if not secrets.compare_digest(sent, key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def check_admin(request: Request) -> None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("basic "):
        try:
            user, _, pw = base64.b64decode(auth[6:]).decode().partition(":")
            if secrets.compare_digest(user, "admin") and secrets.compare_digest(pw, settings.admin_password):
                return
        except Exception:
            pass
    raise HTTPException(status_code=401, detail="Admin login required",
                        headers={"WWW-Authenticate": 'Basic realm="CheezyTranscoder admin"'})


# --------------------------------------------------------------------------- pages
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index() -> HTMLResponse:
    return HTMLResponse((STATIC / "index.html").read_text())


@app.get("/settings", response_class=HTMLResponse, include_in_schema=False)
async def settings_page(request: Request) -> HTMLResponse:
    check_admin(request)
    return HTMLResponse((STATIC / "settings.html").read_text())


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "ffmpeg": shutil.which("ffmpeg") is not None,
            "jobs": len(JOBS), "active": limiter.active}


# --------------------------------------------------------------------------- public API
CHOICES = {
    "mode": ["copy", "transcode"],
    "container": sorted(ffmpeg.CONTAINERS),
    "video_codec": sorted(ffmpeg.VIDEO_CODECS),
    "audio_codec": sorted(ffmpeg.AUDIO_CODECS),
    "pix_fmt": sorted(ffmpeg.PIX_FMTS),
    "preset": ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium",
               "slow", "slower", "veryslow"],
}


@app.get("/api/config")
async def public_config(request: Request) -> dict[str, Any]:
    return {
        "site_title": settings.get("site_title"),
        "public_url": public_base(request),
        "requires_api_key": bool(settings.get("api_key")),
        "allow_user_options": settings.get("allow_user_options"),
        "max_upload_mb": settings.get("max_upload_mb"),
        "retention_minutes": settings.get("retention_minutes"),
        "job_defaults": settings.get("job_defaults"),
        "choices": CHOICES,
        "input_extensions": sorted(ffmpeg.INPUT_EXT),
    }


async def _create_job(request: Request) -> Job:
    check_api_key(request)
    form = await request.form()
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise HTTPException(status_code=400, detail="Missing 'file' field")
    name = Path(upload.filename or "").name
    ext = Path(name).suffix.lower()
    if ext not in ffmpeg.INPUT_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext or '?'}'")

    raw = {k: v for k, v in form.items() if k != "file" and isinstance(v, str)}
    defaults = settings.get("job_defaults")
    if not settings.get("allow_user_options"):
        raw = {}
    try:
        opts = ffmpeg.validate_options(raw, defaults)
    except ffmpeg.OptionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    jid = secrets.token_urlsafe(16)
    jdir = WORK_DIR / jid
    jdir.mkdir(parents=True)
    src = jdir / f"input{ext}"
    limit = int(settings.get("max_upload_mb")) * 1024 * 1024
    written = 0
    try:
        with src.open("wb") as fh:
            while chunk := await upload.read(1024 * 1024):
                written += len(chunk)
                if written > limit:
                    raise HTTPException(status_code=413,
                                        detail=f"File exceeds {settings.get('max_upload_mb')} MB")
                fh.write(chunk)
        if written == 0:
            raise HTTPException(status_code=400, detail="Empty file")
    except BaseException:
        shutil.rmtree(jdir, ignore_errors=True)
        raise
    finally:
        await upload.close()

    job = Job(id=jid, original_name=name, options=opts, dir=jdir)
    JOBS[jid] = job
    job.task = asyncio.create_task(process(job, src))
    return job


@app.post("/api/jobs", status_code=202)
async def create_job(request: Request) -> dict[str, Any]:
    """Upload a video (multipart field `file`) plus any option fields. Returns a job."""
    job = await _create_job(request)
    return job_view(job, request)


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict[str, Any]:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    return job_view(job, request)


@app.get("/api/jobs/{job_id}/download")
async def download(job_id: str) -> FileResponse:
    job = JOBS.get(job_id)
    if not job or job.status != "done" or not job.output or not job.output.exists():
        raise HTTPException(status_code=404, detail="File not ready or expired")
    return FileResponse(job.output, media_type="application/octet-stream",
                        filename=job.download_name)


@app.delete("/api/jobs/{job_id}", status_code=204)
async def remove_job(job_id: str) -> Response:
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    delete_job(job_id)
    return Response(status_code=204)


@app.post("/strip")
async def strip_sync(request: Request):
    """Synchronous convenience endpoint: upload and get the cleaned file back directly."""
    job = await _create_job(request)
    assert job.task
    await asyncio.shield(job.task)
    if job.status != "done" or not job.output:
        jid = job.id
        err = job.error
        delete_job(jid)
        raise HTTPException(status_code=422, detail=err or "Processing failed")
    return FileResponse(job.output, media_type="application/octet-stream",
                        filename=job.download_name,
                        background=BackgroundTask(delete_job, job.id))


# --------------------------------------------------------------------------- admin API
@app.get("/api/admin/settings")
async def admin_get(request: Request) -> dict[str, Any]:
    check_admin(request)
    return {"settings": settings.snapshot(), "choices": CHOICES,
            "jobs": [job_view(j, request) for j in JOBS.values()]}


@app.put("/api/admin/settings")
async def admin_put(request: Request) -> dict[str, Any]:
    check_admin(request)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Expected JSON object")
    patch: dict[str, Any] = {}
    try:
        if "site_title" in body:
            patch["site_title"] = str(body["site_title"])[:80] or "CheezyTranscoder"
        if "public_url" in body:
            pu = str(body["public_url"]).strip().rstrip("/")
            if pu:
                if "://" not in pu:
                    pu = "https://" + pu
                p = urlparse(pu)
                if p.scheme not in ("http", "https") or not p.hostname:
                    raise ValueError("public_url must be like https://video.example.com")
                pu = f"{p.scheme}://{p.netloc}"
            patch["public_url"] = pu
        for k in ("enforce_domain", "allow_user_options"):
            if k in body:
                patch[k] = bool(body[k])
        if "cors_origins" in body:
            patch["cors_origins"] = str(body["cors_origins"])
        if "api_key" in body:
            patch["api_key"] = str(body["api_key"]).strip()
        for k, lo, hi in (("max_upload_mb", 1, 102400), ("ffmpeg_timeout", 10, 86400),
                          ("max_concurrent_jobs", 1, 64), ("retention_minutes", 1, 10080)):
            if k in body:
                v = int(body[k])
                if not lo <= v <= hi:
                    raise ValueError(f"{k} must be between {lo} and {hi}")
                patch[k] = v
        if "job_defaults" in body and isinstance(body["job_defaults"], dict):
            patch["job_defaults"] = ffmpeg.validate_options(body["job_defaults"], DEFAULT_JOB_OPTIONS)
    except (ValueError, TypeError, ffmpeg.OptionError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    snap = settings.update(patch)
    async with limiter.cond:
        limiter.cond.notify_all()
    return {"settings": snap}


@app.delete("/api/admin/jobs/{job_id}", status_code=204)
async def admin_delete_job(job_id: str, request: Request) -> Response:
    check_admin(request)
    delete_job(job_id)
    return Response(status_code=204)
