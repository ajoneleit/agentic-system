"""Task execution result data structures with artifact integration."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from src.core.interfaces import Artifact


@dataclass
class TaskResult:
    """Result of a task execution by an agent with artifact tracking."""
    
    task_id: UUID
    agent_id: UUID
    success: bool
    
    # Artifact integration
    artifacts: List[UUID] = field(default_factory=list)  # All artifact IDs created
    primary_artifact: Optional[UUID] = None  # Main artifact for this task
    
    # Execution details
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    execution_time: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # Metrics and metadata
    metrics: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Verification results
    compilation_success: Optional[bool] = None
    test_results: Optional[Dict[str, Any]] = None
    
    def add_artifact(self, artifact_id: UUID, is_primary: bool = False) -> None:
        """Add an artifact to the task result.
        
        Args:
            artifact_id: ID of the artifact to add
            is_primary: Whether this is the primary artifact
        """
        if artifact_id not in self.artifacts:
            self.artifacts.append(artifact_id)
        
        if is_primary:
            self.primary_artifact = artifact_id
    
    def add_error(self, error: str) -> None:
        """Add an error to the result."""
        self.errors.append(error)
        self.success = False
    
    def add_warning(self, warning: str) -> None:
        """Add a warning to the result."""
        self.warnings.append(warning)
    
    def set_metrics(self, **kwargs) -> None:
        """Set metrics for the task result."""
        self.metrics.update(kwargs)


@dataclass
class ExecutionResult:
    """Result of processing a complete user request with artifacts."""
    
    request_id: UUID
    success: bool
    
    # Artifact management
    artifacts: List[Artifact] = field(default_factory=list)
    project_manifest: Optional[Artifact] = None
    artifact_storage_path: Optional[Path] = None
    
    # Task results
    task_results: List[TaskResult] = field(default_factory=list)
    
    # Execution summary
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    
    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_execution_time: float = 0.0
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def success_rate(self) -> float:
        """Calculate the success rate of task execution."""
        if self.total_tasks == 0:
            return 0.0
        return self.completed_tasks / self.total_tasks
    
    def add_task_result(self, result: TaskResult) -> None:
        """Add a task result to the execution result."""
        self.task_results.append(result)
        self.total_tasks += 1
        
        if result.success:
            self.completed_tasks += 1
        else:
            self.failed_tasks += 1
            self.success = False
    
    def add_artifact(self, artifact: Artifact) -> None:
        """Add an artifact to the execution result."""
        if artifact not in self.artifacts:
            self.artifacts.append(artifact)
    
    def set_project_manifest(self, manifest: Artifact) -> None:
        """Set the project manifest artifact."""
        self.project_manifest = manifest
        self.add_artifact(manifest)