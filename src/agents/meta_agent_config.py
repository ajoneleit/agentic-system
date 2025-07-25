"""Meta agent configuration module.

This module provides configuration classes for the meta agent system.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    retry_delay: float = 1.0
    retry_backoff: float = 2.0
    timeout: int = 300
    exponential_backoff: bool = True


@dataclass
class TaskExecutionConfig:
    """Configuration for task execution."""

    max_parallel_tasks: int = 3
    task_timeout: int = 300
    verification_enabled: bool = True
    verification_timeout: int = 120
    max_task_retries: int = 2
    dependency_timeout: int = 600


@dataclass
class ProjectConfig:
    """Configuration for project management."""

    base_storage_path: Path = field(default_factory=lambda: Path("./projects"))
    artifact_storage_path: Path = field(default_factory=lambda: Path("./artifacts"))
    workspace_cleanup: bool = True
    max_project_size_mb: int = 1000
    backup_enabled: bool = True


@dataclass
class AgentConfig:
    """Configuration for agent management."""

    max_active_agents: int = 10
    agent_timeout: int = 300
    agent_memory_limit_mb: int = 512
    agent_cleanup_interval: int = 3600
    default_agent_role: str = "core_logic"


@dataclass
class DecompositionConfig:
    """Configuration for task decomposition."""

    max_task_depth: int = 5
    min_task_complexity: int = 1
    max_task_complexity: int = 10
    dependency_analysis: bool = True
    cache_decompositions: bool = True
    cache_ttl: int = 3600


@dataclass
class VerificationConfig:
    """Configuration for verification system."""

    compiler_verification: bool = True
    test_verification: bool = True
    coverage_threshold: float = 0.9  # Standard 90% coverage target
    quality_gates: bool = True
    verification_parallel: bool = True
    max_verification_time: int = 600


@dataclass
class LoggingConfig:
    """Configuration for logging."""

    log_level: str = "INFO"
    log_format: str = "json"
    log_file: Optional[str] = None
    structured_logging: bool = True
    performance_logging: bool = True
    error_reporting: bool = True


@dataclass
class MetaAgentConfig:
    """Main configuration for the meta agent system."""

    # Sub-configurations
    retry: RetryConfig = field(default_factory=RetryConfig)
    task_execution: TaskExecutionConfig = field(default_factory=TaskExecutionConfig)
    project: ProjectConfig = field(default_factory=ProjectConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    decomposition: DecompositionConfig = field(default_factory=DecompositionConfig)
    verification: VerificationConfig = field(default_factory=VerificationConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # API configurations
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    openai_model: str = "gpt-4"
    claude_model: str = "claude-3-opus-20240229"

    # System configurations
    debug_mode: bool = False
    performance_monitoring: bool = True
    health_check_interval: int = 300
    system_timeout: int = 3600

    # Feature flags
    enable_caching: bool = True
    enable_parallel_execution: bool = True
    enable_auto_retry: bool = True
    enable_verification: bool = True
    enable_monitoring: bool = True

    # Custom configurations
    custom_settings: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> list[str]:
        """Validate configuration settings.

        Returns:
            List of validation errors

        """
        errors = []

        # Validate API keys
        if not self.openai_api_key:
            errors.append("OpenAI API key is required")
        if not self.anthropic_api_key:
            errors.append("Anthropic API key is required")

        # Validate paths
        if not self.project.base_storage_path.exists():
            try:
                self.project.base_storage_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create base storage path: {e}")

        if not self.project.artifact_storage_path.exists():
            try:
                self.project.artifact_storage_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create artifact storage path: {e}")

        # Validate numeric ranges
        if self.task_execution.max_parallel_tasks < 1:
            errors.append("max_parallel_tasks must be at least 1")
        if self.task_execution.max_parallel_tasks > 20:
            errors.append("max_parallel_tasks should not exceed 20")

        if self.retry.max_retries < 0:
            errors.append("max_retries cannot be negative")
        if self.retry.max_retries > 10:
            errors.append("max_retries should not exceed 10")

        if self.verification.coverage_threshold < 0 or self.verification.coverage_threshold > 1:
            errors.append("coverage_threshold must be between 0 and 1")

        # Validate timeouts
        if self.task_execution.task_timeout < 30:
            errors.append("task_timeout should be at least 30 seconds")
        if self.task_execution.task_timeout > 3600:
            errors.append("task_timeout should not exceed 1 hour")

        # Validate models
        valid_openai_models = ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"]
        if self.openai_model not in valid_openai_models:
            errors.append(f"Invalid OpenAI model: {self.openai_model}")

        valid_claude_models = [
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
        ]
        if self.claude_model not in valid_claude_models:
            errors.append(f"Invalid Claude model: {self.claude_model}")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary.

        Returns:
            Configuration as dictionary

        """
        return {
            "retry": {
                "max_retries": self.retry.max_retries,
                "retry_delay": self.retry.retry_delay,
                "retry_backoff": self.retry.retry_backoff,
                "timeout": self.retry.timeout,
                "exponential_backoff": self.retry.exponential_backoff,
            },
            "task_execution": {
                "max_parallel_tasks": self.task_execution.max_parallel_tasks,
                "task_timeout": self.task_execution.task_timeout,
                "verification_enabled": self.task_execution.verification_enabled,
                "verification_timeout": self.task_execution.verification_timeout,
                "max_task_retries": self.task_execution.max_task_retries,
                "dependency_timeout": self.task_execution.dependency_timeout,
            },
            "project": {
                "base_storage_path": str(self.project.base_storage_path),
                "artifact_storage_path": str(self.project.artifact_storage_path),
                "workspace_cleanup": self.project.workspace_cleanup,
                "max_project_size_mb": self.project.max_project_size_mb,
                "backup_enabled": self.project.backup_enabled,
            },
            "agent": {
                "max_active_agents": self.agent.max_active_agents,
                "agent_timeout": self.agent.agent_timeout,
                "agent_memory_limit_mb": self.agent.agent_memory_limit_mb,
                "agent_cleanup_interval": self.agent.agent_cleanup_interval,
                "default_agent_role": self.agent.default_agent_role,
            },
            "decomposition": {
                "max_task_depth": self.decomposition.max_task_depth,
                "min_task_complexity": self.decomposition.min_task_complexity,
                "max_task_complexity": self.decomposition.max_task_complexity,
                "dependency_analysis": self.decomposition.dependency_analysis,
                "cache_decompositions": self.decomposition.cache_decompositions,
                "cache_ttl": self.decomposition.cache_ttl,
            },
            "verification": {
                "compiler_verification": self.verification.compiler_verification,
                "test_verification": self.verification.test_verification,
                "coverage_threshold": self.verification.coverage_threshold,
                "quality_gates": self.verification.quality_gates,
                "verification_parallel": self.verification.verification_parallel,
                "max_verification_time": self.verification.max_verification_time,
            },
            "logging": {
                "log_level": self.logging.log_level,
                "log_format": self.logging.log_format,
                "log_file": self.logging.log_file,
                "structured_logging": self.logging.structured_logging,
                "performance_logging": self.logging.performance_logging,
                "error_reporting": self.logging.error_reporting,
            },
            "api": {"openai_model": self.openai_model, "claude_model": self.claude_model},
            "system": {
                "debug_mode": self.debug_mode,
                "performance_monitoring": self.performance_monitoring,
                "health_check_interval": self.health_check_interval,
                "system_timeout": self.system_timeout,
            },
            "features": {
                "enable_caching": self.enable_caching,
                "enable_parallel_execution": self.enable_parallel_execution,
                "enable_auto_retry": self.enable_auto_retry,
                "enable_verification": self.enable_verification,
                "enable_monitoring": self.enable_monitoring,
            },
            "custom": self.custom_settings,
        }

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any]) -> "MetaAgentConfig":
        """Create configuration from dictionary.

        Args:
            config_dict: Configuration dictionary

        Returns:
            MetaAgentConfig instance

        """
        config = cls()

        # Update retry config
        if "retry" in config_dict:
            retry_dict = config_dict["retry"]
            config.retry = RetryConfig(
                max_retries=retry_dict.get("max_retries", config.retry.max_retries),
                retry_delay=retry_dict.get("retry_delay", config.retry.retry_delay),
                retry_backoff=retry_dict.get("retry_backoff", config.retry.retry_backoff),
                timeout=retry_dict.get("timeout", config.retry.timeout),
                exponential_backoff=retry_dict.get(
                    "exponential_backoff", config.retry.exponential_backoff
                ),
            )

        # Update task execution config
        if "task_execution" in config_dict:
            task_dict = config_dict["task_execution"]
            config.task_execution = TaskExecutionConfig(
                max_parallel_tasks=task_dict.get(
                    "max_parallel_tasks", config.task_execution.max_parallel_tasks
                ),
                task_timeout=task_dict.get("task_timeout", config.task_execution.task_timeout),
                verification_enabled=task_dict.get(
                    "verification_enabled", config.task_execution.verification_enabled
                ),
                verification_timeout=task_dict.get(
                    "verification_timeout", config.task_execution.verification_timeout
                ),
                max_task_retries=task_dict.get(
                    "max_task_retries", config.task_execution.max_task_retries
                ),
                dependency_timeout=task_dict.get(
                    "dependency_timeout", config.task_execution.dependency_timeout
                ),
            )

        # Update other configurations...
        # (Similar pattern for other config sections)

        # Update top-level settings
        config.openai_api_key = config_dict.get("openai_api_key")
        config.anthropic_api_key = config_dict.get("anthropic_api_key")
        config.openai_model = config_dict.get("openai_model", config.openai_model)
        config.claude_model = config_dict.get("claude_model", config.claude_model)
        config.debug_mode = config_dict.get("debug_mode", config.debug_mode)
        config.custom_settings = config_dict.get("custom", {})

        return config

    def update_from_env(self) -> None:
        """Update configuration from environment variables."""
        import os

        # API keys
        if os.getenv("OPENAI_API_KEY"):
            self.openai_api_key = os.getenv("OPENAI_API_KEY")
        if os.getenv("ANTHROPIC_API_KEY"):
            self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

        # Models
        if os.getenv("OPENAI_MODEL"):
            self.openai_model = os.getenv("OPENAI_MODEL")
        if os.getenv("CLAUDE_MODEL"):
            self.claude_model = os.getenv("CLAUDE_MODEL")

        # System settings
        if os.getenv("DEBUG_MODE"):
            self.debug_mode = os.getenv("DEBUG_MODE").lower() == "true"
        if os.getenv("MAX_PARALLEL_TASKS"):
            self.task_execution.max_parallel_tasks = int(os.getenv("MAX_PARALLEL_TASKS"))
        if os.getenv("TASK_TIMEOUT"):
            self.task_execution.task_timeout = int(os.getenv("TASK_TIMEOUT"))

        # Paths
        if os.getenv("BASE_STORAGE_PATH"):
            self.project.base_storage_path = Path(os.getenv("BASE_STORAGE_PATH"))
        if os.getenv("ARTIFACT_STORAGE_PATH"):
            self.project.artifact_storage_path = Path(os.getenv("ARTIFACT_STORAGE_PATH"))

        # Logging
        if os.getenv("LOG_LEVEL"):
            self.logging.log_level = os.getenv("LOG_LEVEL")
        if os.getenv("LOG_FORMAT"):
            self.logging.log_format = os.getenv("LOG_FORMAT")
        if os.getenv("LOG_FILE"):
            self.logging.log_file = os.getenv("LOG_FILE")


def load_config(config_path: Optional[Path] = None) -> MetaAgentConfig:
    """Load configuration from file or environment.

    Args:
        config_path: Optional path to configuration file

    Returns:
        MetaAgentConfig instance

    """
    config = MetaAgentConfig()

    # Load from file if provided
    if config_path and config_path.exists():
        import json

        with open(config_path) as f:
            config_dict = json.load(f)
            config = MetaAgentConfig.from_dict(config_dict)

    # Override with environment variables
    config.update_from_env()

    return config


def save_config(config: MetaAgentConfig, config_path: Path) -> None:
    """Save configuration to file.

    Args:
        config: Configuration to save
        config_path: Path to save configuration to

    """
    import json

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config.to_dict(), f, indent=2)
