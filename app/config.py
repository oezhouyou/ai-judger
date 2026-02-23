from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Validates at startup — missing or invalid values cause an immediate,
    clear error rather than a cryptic failure later at request time.
    """

    anthropic_api_key: str = Field(
        ..., description="Anthropic API key (required)"
    )
    claude_model: str = Field(
        default="claude-opus-4-6",
        description="Claude model ID for analysis",
    )
    max_upload_size_mb: int = Field(
        default=50, ge=1, le=500, description="Maximum upload size in MB"
    )
    max_video_frames: int = Field(
        default=20, ge=1, le=100, description="Maximum frames to extract from video"
    )
    log_level: str = Field(
        default="info", description="Logging level (debug, info, warning, error)"
    )
    cors_origins: str = Field(
        default="*",
        description="Allowed CORS origins (comma-separated, or * for all)",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated origins into a list."""
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"debug", "info", "warning", "error", "critical"}
        if v.lower() not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v.lower()

    @field_validator("anthropic_api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        if not v or v.startswith("sk-ant-xxxxx"):
            raise ValueError(
                "ANTHROPIC_API_KEY is not set or still contains the placeholder. "
                "Copy .env.example to .env and set a real API key."
            )
        return v

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — parsed once, reused everywhere."""
    return Settings()
