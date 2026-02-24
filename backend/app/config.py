"""
Configuration module for the Chart Widget Builder backend.

Loads environment variables and provides application settings.
"""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    database_url: str = "sqlite:///./chart_builder.db"
    secret_key: str = "change-me-to-a-random-string"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    context_token_limit: int = 64000

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
        ]

    class Config:
        """Pydantic settings configuration."""

        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
