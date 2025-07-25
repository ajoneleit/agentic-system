"""
Core interfaces and abstract base classes for the verification system.

This module defines the fundamental abstractions that all verification
components must implement, ensuring consistency and extensibility.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.core.interfaces import Artifact
from src.verification.models import LanguageType, VerificationStage, VerificationStatus


@dataclass
class VerificationContext:
    """Context information for verification execution."""
    
    # File and project information
    file_path: Path
    project_root: Path
    language: LanguageType
    
    # Verification configuration
    stages: List[VerificationStage] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    
    # Environment and dependencies
    working_directory: Optional[Path] = None
    environment_vars: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 300
    
    # Integration points
    artifact_id: Optional[str] = None
    task_id: Optional[str] = None
    session_id: Optional[str] = None
    
    # Execution metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationResult:
    """Result of a verification operation."""
    
    # Basic result information
    success: bool
    status: VerificationStatus
    stage: VerificationStage
    language: LanguageType
    
    # Timing information
    started_at: datetime
    completed_at: Optional[datetime] = None
    execution_time: float = 0.0
    
    # Output and errors
    output: str = ""
    error_message: str = ""
    error_details: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    
    # Metrics and analysis
    metrics: Dict[str, Any] = field(default_factory=dict)
    line_count: Optional[int] = None
    file_size: Optional[int] = None
    
    # Configuration used
    config: Dict[str, Any] = field(default_factory=dict)
    environment_info: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration(self) -> float:
        """Get execution duration in seconds."""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return self.execution_time


@dataclass
class VerificationSummary:
    """Summary of a complete verification session."""
    
    # Session information
    session_id: str
    total_stages: int
    completed_stages: int
    
    # Results breakdown
    successful_stages: int = 0
    failed_stages: int = 0
    skipped_stages: int = 0
    error_stages: int = 0
    
    # Overall status
    overall_success: bool = False
    overall_status: VerificationStatus = VerificationStatus.PENDING
    
    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    total_execution_time: float = 0.0
    
    # Detailed results
    stage_results: List[VerificationResult] = field(default_factory=list)
    artifacts_verified: Set[str] = field(default_factory=set)
    
    # Summary metrics
    coverage_metrics: Dict[str, float] = field(default_factory=dict)
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    quality_metrics: Dict[str, Any] = field(default_factory=dict)


class VerifierInterface(ABC):
    """Abstract base class for all verifiers."""
    
    @property
    @abstractmethod
    def supported_languages(self) -> Set[LanguageType]:
        """Return the set of languages this verifier supports."""
        pass
    
    @property
    @abstractmethod
    def verification_stage(self) -> VerificationStage:
        """Return the verification stage this verifier implements."""
        pass
    
    @abstractmethod
    async def verify(self, context: VerificationContext) -> VerificationResult:
        """
        Perform verification on the given context.
        
        Args:
            context: Verification context with file and configuration
            
        Returns:
            VerificationResult with detailed results
        """
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check if this verifier is available and properly configured.
        
        Returns:
            True if verifier can be used, False otherwise
        """
        pass
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check on the verifier.
        
        Returns:
            Dictionary with health status and diagnostics
        """
        try:
            available = await self.is_available()
            return {
                "available": available,
                "stage": self.verification_stage.value,
                "languages": [lang.value for lang in self.supported_languages],
                "status": "healthy" if available else "unavailable"
            }
        except Exception as e:
            return {
                "available": False,
                "status": "error",
                "error": str(e)
            }


class CompilerVerifierInterface(VerifierInterface):
    """Interface for compiler/syntax verification."""
    
    @property
    def verification_stage(self) -> VerificationStage:
        return VerificationStage.COMPILER
    
    @abstractmethod
    async def check_syntax(self, file_path: Path, context: VerificationContext) -> VerificationResult:
        """Check syntax of the given file."""
        pass
    
    @abstractmethod
    async def check_types(self, file_path: Path, context: VerificationContext) -> VerificationResult:
        """Check types in the given file (if supported)."""
        pass


class TestVerifierInterface(VerifierInterface):
    """Interface for test execution verification."""
    
    @property
    def verification_stage(self) -> VerificationStage:
        return VerificationStage.TEST
    
    @abstractmethod
    async def discover_tests(self, context: VerificationContext) -> List[Path]:
        """Discover test files in the project."""
        pass
    
    @abstractmethod
    async def run_tests(self, test_files: List[Path], context: VerificationContext) -> VerificationResult:
        """Run the specified test files."""
        pass
    
    @abstractmethod
    async def get_coverage(self, context: VerificationContext) -> Dict[str, Any]:
        """Get test coverage information if available."""
        pass


class VerificationPipelineInterface(ABC):
    """Interface for verification pipeline orchestration."""
    
    @abstractmethod
    async def execute(self, context: VerificationContext) -> VerificationSummary:
        """
        Execute the complete verification pipeline.
        
        Args:
            context: Verification context
            
        Returns:
            VerificationSummary with complete results
        """
        pass
    
    @abstractmethod
    async def add_verifier(self, verifier: VerifierInterface) -> None:
        """Add a verifier to the pipeline."""
        pass
    
    @abstractmethod
    async def remove_verifier(self, stage: VerificationStage, language: LanguageType) -> None:
        """Remove a verifier from the pipeline."""
        pass
    
    @abstractmethod
    async def get_verifiers(self) -> Dict[VerificationStage, List[VerifierInterface]]:
        """Get all configured verifiers."""
        pass


class VerificationServiceInterface(ABC):
    """Interface for the verification service that integrates with the system."""
    
    @abstractmethod
    async def verify_artifact(self, artifact: Artifact, stages: List[VerificationStage] = None) -> VerificationSummary:
        """Verify a specific artifact."""
        pass
    
    @abstractmethod
    async def verify_file(self, file_path: Path, language: LanguageType = None) -> VerificationSummary:
        """Verify a specific file."""
        pass
    
    @abstractmethod
    async def verify_project(self, project_root: Path) -> VerificationSummary:
        """Verify an entire project."""
        pass
    
    @abstractmethod
    async def get_verification_history(self, artifact_id: str = None, limit: int = 100) -> List[VerificationSummary]:
        """Get verification history."""
        pass
    
    @abstractmethod
    async def get_metrics(self, period_days: int = 7) -> Dict[str, Any]:
        """Get verification metrics for the specified period."""
        pass