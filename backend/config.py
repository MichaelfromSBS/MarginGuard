from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", populate_by_name=True, hide_input_in_errors=True)

    ai_mode: Literal["mock", "openrouter"] = "mock"
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_model: str = ""
    ai_timeout_seconds: float = Field(default=60, ge=1, le=180)
    ai_max_output_tokens: int = Field(default=1800, ge=128, le=8192)
    database_path: Path = Field(default=ROOT / "data" / "marginguard.db", validation_alias="MARGINGUARD_DATABASE_PATH")
    upload_directory: Path = Field(default=ROOT / "data" / "uploads", validation_alias="MARGINGUARD_UPLOAD_DIRECTORY")
    extraction_max_output_tokens: int = Field(default=6000, ge=512, le=8192, validation_alias="MARGINGUARD_EXTRACTION_MAX_OUTPUT_TOKENS")
    processing_mode: Literal["worker", "inline"] = Field(default="worker", validation_alias="MARGINGUARD_PROCESSING_MODE")
    inbox_directory: Path = Field(default=ROOT / "inbox", validation_alias="MARGINGUARD_INBOX_DIRECTORY")
    worker_poll_seconds: float = Field(default=2, ge=0.2, le=30, validation_alias="MARGINGUARD_WORKER_POLL_SECONDS")
    file_stable_seconds: float = Field(default=2, ge=0, le=60, validation_alias="MARGINGUARD_FILE_STABLE_SECONDS")
    extraction_max_attempts: int = Field(default=3, ge=1, le=5, validation_alias="MARGINGUARD_EXTRACTION_MAX_ATTEMPTS")
    alert_ai_explanations: bool = Field(default=True, validation_alias="MARGINGUARD_ALERT_AI_EXPLANATIONS")
    price_spike_pct: float = Field(default=10, ge=0, le=1000, validation_alias="MARGINGUARD_PRICE_SPIKE_PCT")
    projected_cost_increase_usd: float = Field(default=50, ge=0, validation_alias="MARGINGUARD_PROJECTED_COST_INCREASE_USD")
    sales_drop_pct: float = Field(default=30, ge=0, le=100, validation_alias="MARGINGUARD_SALES_DROP_PCT")
    sales_drop_min_units: float = Field(default=10, ge=0, validation_alias="MARGINGUARD_SALES_DROP_MIN_UNITS")
    sales_alert_recent_days: int = Field(default=7, ge=1, le=56, validation_alias="MARGINGUARD_SALES_ALERT_RECENT_DAYS")

    @field_validator("database_path", "upload_directory", "inbox_directory")
    @classmethod
    def resolve_database_path(cls, value: Path) -> Path:
        return (ROOT / value).resolve() if not value.is_absolute() else value.resolve()
