"""Base classes and interfaces for the verification system."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from src.core.interfaces import Artifact, ArtifactType
from src.utils.app_logging import get_logger

logger = get_logger(__name__)


class VerificationType(Enum):
    """Types of verification that can be performed."""

    SYNTAX = "syntax"  # Basic syntax checking
    COMPILATION = "compilation"  # Full compilation check
    TEST = "test"  # Unit test execution
    INTEGRATION = "integration"  # Integration test execution
    STYLE = "style"  # Code style/linting
    SECURITY = "security"  # Security vulnerability scanning
    PERFORMANCE = "performance"  # Performance testing


@dataclass
class VerificationMetrics:
    """Metrics collected during verification."""

    execution_time: float = 0.0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0

    # Test-specific metrics
    tests_total: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    coverage_percent: float = 0.0

    # Code quality metrics
    lines_of_code: int = 0
    complexity_score: float = 0.0
    maintainability_index: float = 0.0

    # Custom metrics
    custom: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationResult:
    """Results from verification process."""

    success: bool
    verification_type: VerificationType
    artifact_id: UUID
    verifier_name: str

    # Results
    error_messages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info_messages: list[str] = field(default_factory=list)

    # Metrics
    metrics: VerificationMetrics = field(default_factory=VerificationMetrics)

    # AI-generated suggestions
    suggestions: list[str] = field(default_factory=list)

    # Detailed results (test results, compilation output, etc.)
    details: dict[str, Any] = field(default_factory=dict)

    # Timing
    started_at: datetime = field(default_factory=lambda: datetime.now())
    completed_at: Optional[datetime] = None

    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.error_messages.append(error)
        self.success = False

    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.warnings.append(warning)

    def add_info(self, info: str) -> None:
        """Add an info message."""
        self.info_messages.append(info)

    def add_suggestion(self, suggestion: str) -> None:
        """Add an improvement suggestion."""
        self.suggestions.append(suggestion)

    def complete(self) -> None:
        """Mark verification as complete."""
        self.completed_at = datetime.now()
        if self.started_at:
            self.metrics.execution_time = (self.completed_at - self.started_at).total_seconds()


@dataclass
class VerificationConfig:
    """Configuration for verification process."""

    # What to verify
    enable_syntax_check: bool = True
    enable_compilation: bool = True
    enable_tests: bool = True
    enable_style_check: bool = False
    enable_security_check: bool = False

    # Test configuration
    test_timeout_seconds: int = 30
    test_coverage_threshold: float = 0.9  # 90% - Standard coverage target
    test_patterns: list[str] = field(default_factory=lambda: ["test_*.py", "*_test.py"])

    # Compilation configuration
    compilation_timeout_seconds: int = 60
    target_python_version: str = "3.9"
    strict_mode: bool = True

    # Parallel execution
    max_parallel_verifications: int = 4

    # Output configuration
    verbose: bool = False
    capture_output: bool = True

    # Sandboxing
    use_sandbox: bool = True
    sandbox_memory_limit_mb: int = 512
    sandbox_cpu_limit_percent: int = 50

    # Language-specific settings
    language_settings: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Custom verification paths
    additional_test_paths: list[Path] = field(default_factory=list)
    additional_source_paths: list[Path] = field(default_factory=list)


class VerificationError(Exception):
    """Base exception for verification errors."""

    def __init__(
        self,
        message: str,
        verification_type: Optional[VerificationType] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.verification_type = verification_type
        self.details = details or {}


class BaseVerifier(ABC):
    """Base class for all verifiers."""

    def __init__(self, config: Optional[VerificationConfig] = None):
        """Initialize verifier.

        Args:
            config: Verification configuration

        """
        self.config = config or VerificationConfig()
        self._supported_languages: set[str] = set()
        self._supported_artifact_types: set[ArtifactType] = {
            ArtifactType.SOURCE_CODE,
            ArtifactType.TEST_CODE,
        }

    @property
    @abstractmethod
    def name(self) -> str:
        """Get verifier name."""
        pass

    @property
    @abstractmethod
    def verification_type(self) -> VerificationType:
        """Get the type of verification this verifier performs."""
        pass

    @abstractmethod
    async def verify(
        self, artifact: Artifact, context: Optional[dict[str, Any]] = None
    ) -> VerificationResult:
        """Verify an artifact.

        Args:
            artifact: The artifact to verify
            context: Optional context for verification (e.g., dependencies, environment)

        Returns:
            Verification result

        Raises:
            VerificationError: If verification cannot be performed

        """
        pass

    async def can_verify(self, artifact: Artifact) -> bool:
        """Check if this verifier can handle the given artifact.

        Args:
            artifact: The artifact to check

        Returns:
            True if this verifier can handle the artifact

        """
        # Check artifact type
        if artifact.type not in self._supported_artifact_types:
            return False

        # Check language if applicable
        if self._supported_languages:
            language = self._detect_language(artifact)
            if language not in self._supported_languages:
                return False

        return True

    async def get_verification_context(self, artifact: Artifact) -> dict[str, Any]:
        """Get context needed for verification.

        This might include:
        - Dependencies that need to be available
        - Environment variables
        - Related artifacts
        - Configuration settings

        Args:
            artifact: The artifact to get context for

        Returns:
            Context dictionary

        """
        context = {
            "artifact_id": str(artifact.id),
            "artifact_type": artifact.type.value,
            "artifact_path": str(artifact.path) if artifact.path else None,
            "language": self._detect_language(artifact),
            "config": self.config,
        }

        # Add metadata if available
        if hasattr(artifact, "metadata") and artifact.metadata:
            context["metadata"] = artifact.metadata

        return context

    def _detect_language(self, artifact: Artifact) -> Optional[str]:
        """Detect the programming language of an artifact.

        Args:
            artifact: The artifact to analyze

        Returns:
            Language name or None if cannot detect

        """
        if not artifact.path:
            return None

        # Detect by file extension
        extension_map = {
            ".py": "python",
            ".js": "javascript",
            ".mjs": "javascript",
            ".cjs": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".cpp": "cpp",
            ".c": "c",
            ".cs": "csharp",
            ".rb": "ruby",
            ".php": "php",
        }

        suffix = artifact.path.suffix.lower()
        return extension_map.get(suffix)

    def _create_result(
        self,
        artifact: Artifact,
        success: bool = True,
        error_messages: Optional[list[str]] = None,
        warnings: Optional[list[str]] = None,
    ) -> VerificationResult:
        """Create a verification result.

        Args:
            artifact: The artifact that was verified
            success: Whether verification succeeded
            error_messages: Any error messages
            warnings: Any warning messages

        Returns:
            Verification result

        """
        result = VerificationResult(
            success=success,
            verification_type=self.verification_type,
            artifact_id=artifact.id,
            verifier_name=self.name,
        )

        if error_messages:
            result.error_messages.extend(error_messages)

        if warnings:
            result.warnings.extend(warnings)

        return result
