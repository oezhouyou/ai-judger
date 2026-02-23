import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models import (
    AIGeneratedPrediction,
    AnalysisResponse,
    AudienceSegment,
    DistributionAnalysis,
    JudgeResult,
    TextAnalysisRequest,
    ViralityScore,
)

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_JUDGE_RESULT = {
    "content_type": "text",
    "ai_generated": {
        "probability": 0.75,
        "label": "ai_generated",
        "reasoning": "Uniform paragraph structure and hedging language.",
    },
    "virality": {
        "score": 42,
        "reasoning": "Moderate emotional resonance but niche topic.",
    },
    "distribution": {
        "segments": [
            {
                "audience": "Tech enthusiasts",
                "resonance_reason": "Covers emerging AI tooling.",
            },
            {
                "audience": "Content creators",
                "resonance_reason": "Discusses content authenticity.",
            },
        ]
    },
    "summary": "Likely AI-generated tech commentary with moderate viral potential.",
}


def _mock_claude_response(result_dict: dict, stop_reason: str = "end_turn"):
    """Build a mock response object matching the Anthropic SDK shape."""
    content_block = SimpleNamespace(text=json.dumps(result_dict))
    return SimpleNamespace(content=[content_block], stop_reason=stop_reason)


# ---------------------------------------------------------------------------
# Model validation tests
# ---------------------------------------------------------------------------


class TestModels:
    def test_judge_result_valid(self):
        result = JudgeResult(**SAMPLE_JUDGE_RESULT)
        assert result.content_type == "text"
        assert result.ai_generated.probability == 0.75
        assert result.ai_generated.label == "ai_generated"
        assert result.virality.score == 42
        assert len(result.distribution.segments) == 2

    def test_ai_generated_probability_bounds(self):
        with pytest.raises(ValidationError):
            AIGeneratedPrediction(
                probability=1.5, label="ai_generated", reasoning="test"
            )
        with pytest.raises(ValidationError):
            AIGeneratedPrediction(
                probability=-0.1, label="ai_generated", reasoning="test"
            )

    def test_virality_score_bounds(self):
        with pytest.raises(ValidationError):
            ViralityScore(score=101, reasoning="test")
        with pytest.raises(ValidationError):
            ViralityScore(score=-1, reasoning="test")

    def test_text_analysis_request_rejects_empty(self):
        with pytest.raises(ValidationError):
            TextAnalysisRequest(text="")

    def test_audience_segment_valid(self):
        seg = AudienceSegment(
            audience="Gamers", resonance_reason="High engagement topic"
        )
        assert seg.audience == "Gamers"

    def test_analysis_response_wraps_result(self):
        result = JudgeResult(**SAMPLE_JUDGE_RESULT)
        resp = AnalysisResponse(result=result)
        assert resp.status == "success"
        assert resp.result.content_type == "text"


# ---------------------------------------------------------------------------
# Judge logic tests (mocked Claude API)
# ---------------------------------------------------------------------------


class TestJudgeLogic:
    @pytest.mark.asyncio
    @patch("app.judge.client")
    async def test_analyze_text_returns_judge_result(self, mock_client):
        mock_client.messages = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_claude_response(SAMPLE_JUDGE_RESULT)
        )

        from app.judge import analyze_text

        result = await analyze_text("Some sample text to analyze.")
        assert isinstance(result, JudgeResult)
        assert result.content_type == "text"
        assert 0.0 <= result.ai_generated.probability <= 1.0

    @pytest.mark.asyncio
    @patch("app.judge.client")
    async def test_analyze_text_passes_text_in_message(self, mock_client):
        mock_client.messages = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_claude_response(SAMPLE_JUDGE_RESULT)
        )

        from app.judge import analyze_text

        await analyze_text("Hello world")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert any("Hello world" in block["text"] for block in user_content)

    @pytest.mark.asyncio
    @patch("app.judge.client")
    async def test_analyze_with_images_puts_images_first(self, mock_client):
        mock_client.messages = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_claude_response(
                {**SAMPLE_JUDGE_RESULT, "content_type": "image"}
            )
        )

        from app.judge import analyze_with_images

        images = [{"data": "abc123", "media_type": "image/jpeg"}]
        await analyze_with_images(images, content_type="image")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]

        # First image block should appear before the final instruction text
        image_indices = [
            i for i, b in enumerate(user_content) if b.get("type") == "image"
        ]
        text_indices = [
            i
            for i, b in enumerate(user_content)
            if b.get("type") == "text"
            and "Analyze this" in b.get("text", "")
        ]
        assert image_indices[0] < text_indices[0]

    @pytest.mark.asyncio
    @patch("app.judge.client")
    async def test_handles_refusal(self, mock_client):
        mock_client.messages = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_claude_response(
                SAMPLE_JUDGE_RESULT, stop_reason="refusal"
            )
        )

        from app.judge import analyze_text

        with pytest.raises(ValueError, match="refused"):
            await analyze_text("Bad content")

    @pytest.mark.asyncio
    @patch("app.judge.client")
    async def test_handles_max_tokens(self, mock_client):
        mock_client.messages = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_claude_response(
                SAMPLE_JUDGE_RESULT, stop_reason="max_tokens"
            )
        )

        from app.judge import analyze_text

        with pytest.raises(ValueError, match="truncated"):
            await analyze_text("Very long content")


# ---------------------------------------------------------------------------
# Endpoint tests (mocked Claude API)
# ---------------------------------------------------------------------------


class TestEndpoints:
    def test_health_endpoint(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    @patch("app.main.analyze_text")
    def test_text_endpoint_success(self, mock_analyze):
        mock_analyze.return_value = JudgeResult(**SAMPLE_JUDGE_RESULT)

        resp = client.post(
            "/analyze/text",
            json={"text": "Analyze this content please."},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["result"]["content_type"] == "text"
        assert "ai_generated" in body["result"]
        assert "virality" in body["result"]
        assert "distribution" in body["result"]

    def test_text_endpoint_empty_body(self):
        resp = client.post("/analyze/text", json={"text": ""})
        assert resp.status_code == 422

    def test_text_endpoint_missing_field(self):
        resp = client.post("/analyze/text", json={})
        assert resp.status_code == 422

    def test_video_endpoint_wrong_content_type(self):
        resp = client.post(
            "/analyze/video",
            files={"file": ("test.txt", b"not a video", "text/plain")},
        )
        assert resp.status_code == 400
        assert "Unsupported file type" in resp.json()["detail"]

    def test_url_endpoint_invalid_url(self):
        resp = client.post("/analyze/url", json={"url": "not-a-url"})
        assert resp.status_code == 422
