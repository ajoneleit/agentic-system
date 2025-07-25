"""Configuration settings for the Agentic Coding System.

This module provides centralized configuration management with environment-based
settings, API keys, and model configurations.
"""

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class Environment(str, Enum):
    """Environment types."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class LogLevel(str, Enum):
    """Logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ClaudeModel(str, Enum):
    """Claude model identifiers."""

    HAIKU = "claude-3-haiku-20240307"
    SONNET = "claude-3-sonnet-20240229"
    OPUS = "claude-3-opus-20240229"


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: LogLevel = LogLevel.INFO
    format: str = "json"
    file_path: Optional[Path] = None
    max_file_size_mb: int = 100
    backup_count: int = 5


class Settings(BaseSettings):
    """Application settings."""

    # Project info
    project_name: str = "Agentic Coding System"
    version: str = "1.0.0"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False

    # API Keys
    anthropic_api_key: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")

    # Models
    claude_model: ClaudeModel = ClaudeModel.SONNET
    openai_model: str = "gpt-4"

    # Paths
    base_path: Path = Field(default_factory=lambda: Path.cwd())
    data_path: Path = Field(default_factory=lambda: Path.cwd() / "data")
    logs_path: Path = Field(default_factory=lambda: Path.cwd() / "logs")

    # Logging
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # Features
    enable_caching: bool = True
    enable_monitoring: bool = True
    enable_telemetry: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance.
    
    Returns:
        Settings instance

    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment.
    
    Returns:
        Reloaded settings instance

    """
    global _settings
    _settings = Settings()
    return _settings
