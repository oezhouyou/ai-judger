import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError


class TestSettings:
    def test_defaults_applied(self):
        """Settings should load with sensible defaults when only API key is set."""
        from backend.config import Settings

        # Use _env_file=None to bypass the .env file and test pure defaults
        s = Settings(
            _env_file=None,
            anthropic_api_key="sk-ant-real-key-here",
        )
        assert s.claude_model == "claude-opus-4-6"
        assert s.max_upload_size_mb == 50
        assert s.max_video_frames == 20
        assert s.log_level == "info"
        assert s.cors_origins == "*"
        assert s.cors_origins_list == ["*"]

    def test_missing_api_key_raises(self):
        """Missing ANTHROPIC_API_KEY should raise a clear error."""
        env = {"ANTHROPIC_API_KEY": ""}
        with patch.dict(os.environ, env, clear=False):
            from backend.config import Settings

            with pytest.raises(ValidationError, match="ANTHROPIC_API_KEY"):
                Settings()

    def test_placeholder_api_key_raises(self):
        """Placeholder API key should raise a clear error."""
        env = {"ANTHROPIC_API_KEY": "sk-ant-xxxxxxxxxxxxx"}
        with patch.dict(os.environ, env, clear=False):
            from backend.config import Settings

            with pytest.raises(ValidationError, match="placeholder"):
                Settings()

    def test_invalid_log_level_raises(self):
        """Invalid log level should be rejected."""
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-real-key-here",
            "LOG_LEVEL": "verbose",
        }
        with patch.dict(os.environ, env, clear=False):
            from backend.config import Settings

            with pytest.raises(ValidationError, match="log_level"):
                Settings()

    def test_cors_origins_comma_separated(self):
        """CORS_ORIGINS should accept comma-separated values."""
        from backend.config import Settings

        s = Settings(
            _env_file=None,
            anthropic_api_key="sk-ant-real-key-here",
            cors_origins="http://localhost:3001,https://example.com",
        )
        assert s.cors_origins_list == [
            "http://localhost:3001",
            "https://example.com",
        ]
