import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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
    usage = SimpleNamespace(input_tokens=100, output_tokens=200)
    return SimpleNamespace(
        content=[content_block], stop_reason=stop_reason, usage=usage
    )


def _make_mock_client(response):
    """Create a mock AsyncAnthropic client returning the given response."""
    mock = MagicMock()
    mock.messages = AsyncMock()
    mock.messages.create = AsyncMock(return_value=response)
    return mock


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
    @patch("app.judge._get_client")
    async def test_analyze_text_returns_judge_result(self, mock_get_client):
        mock_get_client.return_value = _make_mock_client(
            _mock_claude_response(SAMPLE_JUDGE_RESULT)
        )

        from app.judge import analyze_text

        result = await analyze_text("Some sample text to analyze.")
        assert isinstance(result, JudgeResult)
        assert result.content_type == "text"
        assert 0.0 <= result.ai_generated.probability <= 1.0

    @pytest.mark.asyncio
    @patch("app.judge._get_client")
    async def test_analyze_text_passes_text_in_message(self, mock_get_client):
        mock_client = _make_mock_client(
            _mock_claude_response(SAMPLE_JUDGE_RESULT)
        )
        mock_get_client.return_value = mock_client

        from app.judge import analyze_text

        await analyze_text("Hello world")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert any("Hello world" in block["text"] for block in user_content)

    @pytest.mark.asyncio
    @patch("app.judge._get_client")
    async def test_analyze_with_images_puts_images_first(self, mock_get_client):
        mock_client = _make_mock_client(
            _mock_claude_response(
                {**SAMPLE_JUDGE_RESULT, "content_type": "image"}
            )
        )
        mock_get_client.return_value = mock_client

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
    @patch("app.judge._get_client")
    async def test_handles_refusal(self, mock_get_client):
        mock_get_client.return_value = _make_mock_client(
            _mock_claude_response(SAMPLE_JUDGE_RESULT, stop_reason="refusal")
        )

        from app.judge import analyze_text

        with pytest.raises(ValueError, match="refused"):
            await analyze_text("Bad content")

    @pytest.mark.asyncio
    @patch("app.judge._get_client")
    async def test_handles_max_tokens(self, mock_get_client):
        mock_get_client.return_value = _make_mock_client(
            _mock_claude_response(SAMPLE_JUDGE_RESULT, stop_reason="max_tokens")
        )

        from app.judge import analyze_text

        with pytest.raises(ValueError, match="truncated"):
            await analyze_text("Very long content")

    @pytest.mark.asyncio
    @patch("app.judge._get_client")
    async def test_handles_invalid_json_response(self, mock_get_client):
        """Claude returning invalid JSON should produce a clear ValueError."""
        bad_response = SimpleNamespace(
            content=[SimpleNamespace(text="not valid json {{{")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=50, output_tokens=10),
        )
        mock_get_client.return_value = _make_mock_client(bad_response)
        # Override the mock to return the bad response directly
        mock_get_client.return_value.messages.create = AsyncMock(
            return_value=bad_response
        )

        from app.judge import analyze_text

        with pytest.raises(ValueError, match="parse"):
            await analyze_text("test")


# ---------------------------------------------------------------------------
# Endpoint tests (mocked Claude API)
# ---------------------------------------------------------------------------


class TestEndpoints:
    def test_health_endpoint(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "version" in body

    def test_health_returns_request_id(self):
        resp = client.get("/health")
        assert "x-request-id" in resp.headers

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


# ---------------------------------------------------------------------------
# Video frame sampling tests
# ---------------------------------------------------------------------------


class TestFrameSampling:
    def test_short_video_gets_few_frames(self):
        from app.video import _compute_frame_count

        # 2-second video should get a handful of frames, not 1 or 20
        count = _compute_frame_count(2.0)
        assert 4 <= count <= 8

    def test_long_video_capped_at_max(self):
        from app.video import _compute_frame_count

        # 1-hour video should hit the max
        count = _compute_frame_count(3600.0)
        assert count == 20

    def test_medium_video_moderate_frames(self):
        from app.video import _compute_frame_count

        # 30-second video should be in the middle range
        count = _compute_frame_count(30.0)
        assert 10 <= count <= 16

    def test_cost_similarity(self):
        from app.video import _compute_frame_count

        short = _compute_frame_count(2.0)
        long = _compute_frame_count(3600.0)
        # The ratio between short and long should be no more than 5x
        assert long / short <= 5

    def test_timestamps_include_start_and_end(self):
        from app.video import _pick_timestamps

        ts = _pick_timestamps(10.0, 5)
        assert ts[0] == 0.0
        assert ts[-1] == pytest.approx(9.9, abs=0.2)

    def test_timestamps_single_frame(self):
        from app.video import _pick_timestamps

        ts = _pick_timestamps(2.0, 1)
        assert ts == [0.0]

    def test_timestamps_two_frames(self):
        from app.video import _pick_timestamps

        ts = _pick_timestamps(5.0, 2)
        assert ts[0] == 0.0
        assert ts[1] == pytest.approx(4.9, abs=0.2)

    def test_timestamps_evenly_spaced(self):
        from app.video import _pick_timestamps

        ts = _pick_timestamps(12.0, 4)
        # Should be roughly [0, 3.97, 7.93, 11.9]
        gaps = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
        # All gaps should be approximately equal
        assert max(gaps) - min(gaps) < 0.1
