# AI Judge Agent

A REST API with a web frontend that evaluates text and video content using Claude's language and vision capabilities. Given any content, it produces an AI-generation probability score, a virality rating, and a distribution analysis identifying which audiences the content would resonate with — along with reasoning for each judgment.

## Quick Start (Docker)

**Prerequisites:** Docker and Docker Compose

```bash
# Configure your API key
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY to your Anthropic API key

# Build and start
make build
make up
```

Open `http://localhost:3001` in your browser.

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make build` | Build all Docker images |
| `make up` | Start all services (detached) |
| `make down` | Stop all services |
| `make logs` | Tail logs from all services |
| `make test` | Run pytest inside the backend container |
| `make dev` | Run backend locally without Docker (`uvicorn --reload`) |

## Local Development (without Docker)

**Prerequisites:** Python 3.11+

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY

uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

## Architecture

```
Browser --> nginx (port 3000) --> /api/* proxy --> uvicorn backend (port 8000)
                |
                └--> static files (index.html, style.css, app.js)
```

- **Frontend**: vanilla HTML/CSS/JS served by nginx, dark-themed UI with tabs for text and video analysis
- **Backend**: FastAPI + Claude API for content analysis
- **Proxy**: nginx strips `/api/` prefix and forwards to the backend

## API Endpoints

### POST /analyze/text

Analyze text content.

```bash
curl -X POST http://localhost:3001/api/analyze/text \
  -H "Content-Type: application/json" \
  -d '{"text": "Your content here..."}'
```

### POST /analyze/video

Analyze a video file (mp4, avi, mov, mkv). Extracts key frames and sends them to Claude's vision API.

```bash
curl -X POST http://localhost:3001/api/analyze/video \
  -F "file=@video.mp4"
```

### GET /health

Health check.

## Response Format

All analysis endpoints return:

```json
{
  "status": "success",
  "result": {
    "content_type": "text",
    "ai_generated": {
      "probability": 0.75,
      "label": "ai_generated",
      "reasoning": "Uniform paragraph structure and hedging language patterns..."
    },
    "virality": {
      "score": 42,
      "reasoning": "Moderate emotional resonance but niche topic..."
    },
    "distribution": {
      "segments": [
        {
          "audience": "Tech enthusiasts",
          "resonance_reason": "Covers emerging AI tooling."
        }
      ]
    },
    "summary": "Likely AI-generated tech commentary with moderate viral potential."
  }
}
```

## Running Tests

```bash
# With Docker
make test

# Without Docker
pytest tests/
```

## Assumptions

- **AI detection is probabilistic, not definitive.** Claude cannot reliably detect AI-generated images visually. The system analyzes content characteristics (writing patterns, structural cues) and expresses appropriate uncertainty. A score near 0.5 labeled "uncertain" is a valid output.
- **Video analysis works by sampling frames.** Up to 10 key frames are extracted at even intervals, resized to 1024px max dimension, and sent to Claude's vision API. This captures the visual gist but may miss transient details.
- **Text input is capped at 50,000 characters** to stay within reasonable token limits for a single Claude API call.

## What I Would Improve With More Time

- **Caching layer** — cache results by content hash to avoid re-analyzing identical content.
- **Rate limiting** — add request rate limiting to protect against abuse and manage Claude API costs.
- **Batch analysis** — accept multiple pieces of content in a single request.
- **Audio track analysis** — for video, also transcribe and analyze the audio alongside visual frames.
- **Confidence calibration** — track predictions over time and calibrate probability scores against known AI/human content.
- **Streaming responses** — use SSE to stream partial results as Claude generates them, improving perceived latency.
- **URL analysis** — fetch and analyze content from URLs, with HTML parsing to extract article text and embedded media.
