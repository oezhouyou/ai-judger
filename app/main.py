import base64
import os

import anthropic
import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.judge import analyze_text, analyze_with_images
from app.models import (
    AnalysisResponse,
    TextAnalysisRequest,
    URLAnalysisRequest,
)
from app.video import extract_frames

app = FastAPI(
    title="AI Judge Agent",
    description=(
        "Analyzes content for AI-generation probability, "
        "virality potential, and audience distribution"
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50")) * 1024 * 1024


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"status": "error", "detail": "An unexpected error occurred."},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/analyze/text", response_model=AnalysisResponse)
async def analyze_text_endpoint(request: TextAnalysisRequest):
    try:
        result = await analyze_text(request.text)
        return AnalysisResponse(result=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except anthropic.APIError as e:
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

    try:
        frames = await extract_frames(video_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = await analyze_with_images(frames, content_type="video")
        return AnalysisResponse(result=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except anthropic.APIError as e:
        raise HTTPException(
            status_code=502, detail=f"Claude API error: {e}"
        )


@app.post("/analyze/url", response_model=AnalysisResponse)
async def analyze_url_endpoint(request: URLAnalysisRequest):
    url = str(request.url)

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=30.0
    ) as http_client:
        try:
            resp = await http_client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=400, detail=f"Could not fetch URL: {e}"
            )

    content_type = (
        resp.headers.get("content-type", "").split(";")[0].strip().lower()
    )

    try:
        if content_type.startswith("text/"):
            result = await analyze_text(resp.text)

        elif content_type.startswith("image/"):
            image_data = base64.standard_b64encode(resp.content).decode(
                "utf-8"
            )
            images = [{"data": image_data, "media_type": content_type}]
            result = await analyze_with_images(
                images, content_type="image"
            )

        elif content_type.startswith("video/"):
            frames = await extract_frames(resp.content)
            result = await analyze_with_images(
                frames, content_type="video"
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported content type: {content_type}",
            )

        return AnalysisResponse(result=result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except anthropic.APIError as e:
        raise HTTPException(
            status_code=502, detail=f"Claude API error: {e}"
        )
