"""Configuration management for the Agentic Coding System.

This module provides centralized configuration management using Pydantic Settings,
supporting environment variables, .env files, and multiple environments.
"""

from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, SecretStr, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Supported execution environments."""
    
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(str, Enum):
    """Supported logging levels."""
    
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ClaudeModel(str, Enum):
    """Available Claude model variants."""
    
    OPUS = "claude-3-opus-20240229"
    SONNET = "claude-3-sonnet-20240229"
    HAIKU = "claude-3-haiku-20240307"


class APISettings(BaseModel):
    """Claude API configuration."""
    
    key: SecretStr = Field(..., description="Anthropic API key")
    base_url: str = Field(
        default="https://api.anthropic.com",
        description="Base URL for Claude API"
    )
    timeout: int = Field(default=300, description="API request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    retry_delay: float = Field(default=1.0, description="Initial retry delay in seconds")
    rate_limit_per_minute: int = Field(default=50, description="Rate limit per minute")


class AgentSettings(BaseModel):
    """Agent system configuration."""
    
    max_parallel_agents: int = Field(default=10, description="Maximum concurrent agents")
    default_model: ClaudeModel = Field(
        default=ClaudeModel.SONNET,
        description="Default Claude model for agents"
    )
    meta_agent_model: ClaudeModel = Field(
        default=ClaudeModel.OPUS,
        description="Model for meta agent (orchestrator)"
    )
    verification_timeout: int = Field(
        default=600,
        description="Verification timeout in seconds"
    )
    max_repair_attempts: int = Field(
        default=5,
        description="Maximum repair loop iterations"
    )
    context_window_buffer: int = Field(
        default=1000,
        description="Token buffer to prevent context overflow"
    )


class VerificationSettings(BaseModel):
    """Code verification configuration."""
    
    enable_compilation_check: bool = Field(default=True)
    enable_test_verification: bool = Field(default=True)
    minimum_coverage: float = Field(
        default=90.0,
        description="Minimum test coverage percentage"
    )
    strict_mode: bool = Field(
        default=True,
        description="Fail on any warning in strict mode"
    )
    supported_languages: List[str] = Field(
        default_factory=lambda: ["python", "javascript", "typescript", "java", "go"]
    )
    
    @validator("minimum_coverage")
    def validate_coverage(cls, v: float) -> float:
        """Ensure coverage is a valid percentage."""
        if not 0 <= v <= 100:
            raise ValueError("Coverage must be between 0 and 100")
        return v


class LearningSettings(BaseModel):
    """Learning system configuration."""
    
    enable_learning: bool = Field(default=True)
    pattern_threshold: int = Field(
        default=3,
        description="Minimum occurrences to identify a pattern"
    )
    memory_retention_days: int = Field(
        default=30,
        description="Days to retain learning data"
    )
    improvement_threshold: float = Field(
        default=0.1,
        description="Minimum improvement to update prompts"
    )


class StorageSettings(BaseModel):
    """Artifact storage configuration."""
    
    base_path: Path = Field(
        default=Path("./artifacts"),
        description="Base path for artifact storage"
    )
    max_versions: int = Field(
        default=10,
        description="Maximum versions to retain per artifact"
    )
    enable_compression: bool = Field(default=True)
    cleanup_interval_hours: int = Field(
        default=24,
        description="Cleanup interval in hours"
    )


class LoggingSettings(BaseModel):
    """Logging configuration."""
    
    level: LogLevel = Field(default=LogLevel.INFO)
    format: str = Field(
        default="json",
        description="Log format (json or console)"
    )
    file_path: Optional[Path] = Field(
        default=None,
        description="Log file path (None for stdout only)"
    )
    max_file_size_mb: int = Field(default=100)
    backup_count: int = Field(default=5)
    include_timestamps: bool = Field(default=True)
    include_context: bool = Field(default=True)


class Settings(BaseSettings):
    """Main application settings.
    
    Settings are loaded from (in order of precedence):
    1. Environment variables
    2. .env file
    3. Default values
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ACS_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Core settings
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Current environment"
    )
    debug: bool = Field(default=False, description="Debug mode")
    project_name: str = Field(
        default="Agentic Coding System",
        description="Project name"
    )
    version: str = Field(default="0.1.0", description="Application version")
    
    # Component settings
    api: APISettings
    agent: AgentSettings = Field(default_factory=AgentSettings)
    verification: VerificationSettings = Field(default_factory=VerificationSettings)
    learning: LearningSettings = Field(default_factory=LearningSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    
    # Performance settings
    enable_profiling: bool = Field(default=False)
    enable_metrics: bool = Field(default=True)
    metrics_port: int = Field(default=9090)
    
    @validator("storage")
    def ensure_storage_path(cls, v: StorageSettings) -> StorageSettings:
        """Create storage directory if it doesn't exist."""
        v.base_path.mkdir(parents=True, exist_ok=True)
        return v
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == Environment.PRODUCTION
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == Environment.DEVELOPMENT
    
    def get_model_for_task(self, task_complexity: str) -> ClaudeModel:
        """Select appropriate model based on task complexity.
        
        Args:
            task_complexity: One of "simple", "medium", "complex"
            
        Returns:
            Appropriate Claude model for the task
        """
        complexity_map = {
            "simple": ClaudeModel.HAIKU,
            "medium": ClaudeModel.SONNET,
            "complex": ClaudeModel.OPUS,
        }
        return complexity_map.get(task_complexity, self.agent.default_model)
    
    def to_dict(self, exclude_secrets: bool = True) -> Dict[str, Any]:
        """Convert settings to dictionary.
        
        Args:
            exclude_secrets: Whether to exclude sensitive information
            
        Returns:
            Dictionary representation of settings
        """
        data = self.model_dump()
        
        if exclude_secrets and "api" in data:
            data["api"]["key"] = "***REDACTED***"
            
        return data


# Global settings instance
settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create settings instance (singleton pattern).
    
    Returns:
        Global settings instance
    """
    global settings
    if settings is None:
        settings = Settings()
    return settings


def reload_settings() -> Settings:
    """Force reload settings from environment.
    
    Returns:
        Reloaded settings instance
    """
    global settings
    settings = Settings()
    return settings