from __future__ import annotations

import traceback
from contextlib import asynccontextmanager

import anthropic
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.judge import analyze_text, analyze_with_images
from app.logging_config import get_logger, setup_logging
from app.middleware import RequestIDMiddleware
from app.models import AnalysisResponse, TextAnalysisRequest
from app.video import extract_frames

log = get_logger(__name__)


# ------------------------------------------------------------------
# Lifespan: startup / shutdown
# ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    log.info(
        "starting",
        model=settings.claude_model,
        max_upload_mb=settings.max_upload_size_mb,
        max_frames=settings.max_video_frames,
        cors=settings.cors_origins_list,
    )
    yield
    log.info("shutting_down")


# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------

app = FastAPI(
    title="AI Judge Agent",
    description=(
        "Analyzes content for AI-generation probability, "
        "virality potential, and audience distribution"
    ),
    version="1.1.0",
    lifespan=lifespan,
)

settings = get_settings()

app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/avi",
    "video/x-msvideo",
    "video/quicktime",
    "video/x-matroska",
}

MAX_UPLOAD_SIZE = settings.max_upload_size_mb * 1024 * 1024


# ------------------------------------------------------------------
# Error handling
# ------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(
        "unhandled_exception",
        exc_type=type(exc).__name__,
        exc_msg=str(exc),
        traceback=traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"status": "error", "detail": "An unexpected error occurred."},
    )


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "version": app.version}


@app.post("/analyze/text", response_model=AnalysisResponse)
async def analyze_text_endpoint(request: TextAnalysisRequest):
    log.info("analyze_text", text_length=len(request.text))
    try:
        result = await analyze_text(request.text)
        log.info("analyze_text_done", content_type=result.content_type)
        return AnalysisResponse(result=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except anthropic.APIError as e:
        log.error("claude_api_error", exc_msg=str(e))
        raise HTTPException(
            status_code=502, detail=f"Claude API error: {e}"
        )


@app.post("/analyze/video", response_model=AnalysisResponse)
async def analyze_video_endpoint(file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. "
            f"Supported: {', '.join(sorted(ALLOWED_VIDEO_TYPES))}",
        )

    video_bytes = await file.read()
    if len(video_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File too large. Maximum size: "
                f"{MAX_UPLOAD_SIZE // (1024 * 1024)}MB"
            ),
        )

    log.info("analyze_video", file_name=file.filename, size_mb=round(len(video_bytes) / 1_048_576, 1))

    try:
        frames = await extract_frames(video_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = await analyze_with_images(frames, content_type="video")
        log.info("analyze_video_done", frame_count=len(frames))
        return AnalysisResponse(result=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except anthropic.APIError as e:
        log.error("claude_api_error", exc_msg=str(e))
        raise HTTPException(
            status_code=502, detail=f"Claude API error: {e}"
        )
