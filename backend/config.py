from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    ai_mode: Literal["mock", "openrouter"] = "mock"
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_model: str = ""
    ai_timeout_seconds: float = Field(default=60, ge=1, le=180)
    ai_max_output_tokens: int = Field(default=1800, ge=128, le=8192)
