"""Refactored Meta Agent implementation.

This is a cleaner, more maintainable version of the MetaAgent that uses
extracted components for better separation of concerns.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from structlog import get_logger

from src.agents.task_decomposer import TaskDecomposer
from src.agents.project_manager import ProjectManager
from src.agents.execution_coordinator import ExecutionCoordinator
from src.agents.meta_agent_config import MetaAgentConfig, load_config
from src.core.interfaces import MetaAgentInterface, Task, TaskContext, Artifact
from src.core.task_result import TaskResult
from src.core.result import Result
from src.core.exceptions import MetaAgentError
from src.core.task_manager import TaskManager
from src.core.artifact_manager import ArtifactManager
from src.clients.openai_client import OpenAIClient
from src.utils.app_logging import log_execution_time

logger = get_logger(__name__)


@dataclass
class ProjectResult:
    """Result of processing a user request."""
    
    project_id: str = ""
    success: bool = True
    artifacts: List[Artifact] = field(default_factory=list)
    execution_time: float = 0.0
    tasks_completed: int = 0
    tasks_failed: int = 0
    success_rate: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    tasks: List[Task] = field(default_factory=list)
    
    @property
    def successful_tasks(self) -> int:
        """Get number of successful tasks."""
        return self.tasks_completed
    
    @property
    def failed_tasks(self) -> int:
        """Get number of failed tasks."""
        return self.tasks_failed


class MetaAgentRefactored(MetaAgentInterface):
    """Refactored Meta Agent with improved architecture.
    
    This version uses extracted components for better separation of concerns:
    - TaskDecomposer: Handles task decomposition and dependency analysis
    - ProjectManager: Manages project storage and lifecycle
    - ExecutionCoordinator: Coordinates task execution and agent management
    - MetaAgentConfig: Centralized configuration management
    """
    
    def __init__(self, config: Optional[MetaAgentConfig] = None):
        """Initialize the refactored Meta Agent.
        
        Args:
            config: Optional configuration, loads default if not provided
        """
        super().__init__()
        
        # Load configuration
        self.config = config or load_config()
        validation_errors = self.config.validate()
        if validation_errors:
            raise MetaAgentError(f"Configuration validation failed: {validation_errors}")
        
        # Initialize OpenAI client (Meta Agent always uses OpenAI O3)
        self.openai_client = OpenAIClient(
            api_key=self.config.openai_api_key,
            model=self.config.openai_model
        )
        
        # Initialize core components
        self.task_decomposer = TaskDecomposer(self.openai_client)
        self.project_manager = ProjectManager(
            base_storage_path=self.config.project.base_storage_path
        )
        self.execution_coordinator = ExecutionCoordinator(
            max_parallel_tasks=self.config.task_execution.max_parallel_tasks,
            task_timeout=self.config.task_execution.task_timeout
        )
        
        # Initialize supporting components
        self.task_manager = TaskManager()
        self.artifact_manager = ArtifactManager(
            storage_path=self.config.project.artifact_storage_path,
            max_memory_cache_size=100,
            enable_compression=True
        )
        
        # Set up artifact manager reference for project manager
        self.project_manager.artifact_manager = self.artifact_manager
        
        # Runtime state
        self._current_project_id: Optional[str] = None
        self._execution_stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_execution_time': 0.0
        }
        
        logger.info(
            "MetaAgent initialized with refactored architecture",
            max_parallel_tasks=self.config.task_execution.max_parallel_tasks,
            openai_model=self.config.openai_model
        )
    
    @log_execution_time("process_request")
    async def process_request(self, user_request: str) -> Result[ProjectResult]:
        """Process a user request end-to-end.
        
        Args:
            user_request: User's coding request
            
        Returns:
            Result containing project execution result or error
        """
        start_time = datetime.now(timezone.utc)
        
        try:
            logger.info(
                "Processing user request",
                request_length=len(user_request),
                timestamp=start_time.isoformat()
            )
            
            # Phase 1: Initialize project storage
            project_init_result = await self.project_manager.initialize_project_storage(user_request)
            if project_init_result.is_failure():
                return Result.failure(project_init_result.error)
            
            project_id = project_init_result.value
            self._current_project_id = project_id
            
            # Phase 2: Decompose request into tasks
            decomposition_result = await self.task_decomposer.decompose_request(user_request, project_id)
            if decomposition_result.is_failure():
                return Result.failure(decomposition_result.error)
            
            tasks = decomposition_result.value
            
            # Phase 3: Create execution context
            context = await self._create_execution_context(project_id, user_request, tasks)
            
            # Phase 4: Execute tasks
            execution_result = await self.execution_coordinator.coordinate_execution(tasks, context)
            if execution_result.is_failure():
                return Result.failure(execution_result.error)
            
            task_results = execution_result.value
            
            # Phase 5: Store execution artifacts
            storage_result = await self.project_manager.store_execution_artifacts(project_id, task_results)
            if storage_result.is_failure():
                logger.warning("Failed to store execution artifacts", error=storage_result.error)
            
            # Phase 6: Create project manifest
            manifest_result = await self.project_manager.create_project_manifest(user_request, task_results)
            if manifest_result.is_failure():
                logger.warning("Failed to create project manifest", error=manifest_result.error)
            
            # Phase 7: Generate final result
            project_result = await self._create_project_result(
                project_id, tasks, task_results, start_time, user_request
            )
            
            # Update statistics
            self._execution_stats['total_requests'] += 1
            if project_result.success:
                self._execution_stats['successful_requests'] += 1
            else:
                self._execution_stats['failed_requests'] += 1
            self._execution_stats['total_execution_time'] += project_result.execution_time
            
            logger.info(
                "Request processing completed",
                project_id=project_id,
                success=project_result.success,
                execution_time=project_result.execution_time,
                tasks_completed=project_result.tasks_completed,
                tasks_failed=project_result.tasks_failed
            )
            
            return Result.success(project_result)
            
        except Exception as e:
            logger.error("Request processing failed", error=str(e), exc_info=True)
            self._execution_stats['failed_requests'] += 1
            return Result.failure(MetaAgentError(f"Failed to process request: {str(e)}"))
    
    async def _create_execution_context(self, project_id: str, user_request: str, tasks: List[Task]) -> TaskContext:
        """Create execution context for tasks.
        
        Args:
            project_id: Project identifier
            user_request: Original user request
            tasks: List of tasks to execute
            
        Returns:
            TaskContext for execution
        """
        project_path = self.config.project.base_storage_path / "projects" / project_id
        workspace_path = project_path / "workspace"
        
        # Ensure workspace directory exists
        workspace_path.mkdir(parents=True, exist_ok=True)
        
        context = TaskContext(
            project_root=project_path,
            shared_memory={
                "project_id": project_id,
                "user_request": user_request,
                "workspace_path": str(workspace_path),
                "project_files": [],
                "task_count": len(tasks)
            },
            parent_task_id=None,
            sibling_task_ids=set(t.id for t in tasks),
            artifact_manager=self.artifact_manager,
            project_id=project_id,
            artifact_metadata_template={
                "project_id": project_id,
                "request": user_request[:200],
                "created_by": "agentic_system",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            artifact_naming_convention="{name}",
            enable_artifact_caching=self.config.enable_caching,
            auto_version_on_change=True,
            link_test_artifacts=True
        )
        
        return context
    
    async def _create_project_result(
        self,
        project_id: str,
        tasks: List[Task],
        task_results: Dict[str, TaskResult],
        start_time: datetime,
        user_request: str
    ) -> ProjectResult:
        """Create final project result.
        
        Args:
            project_id: Project identifier
            tasks: List of executed tasks
            task_results: Dictionary of task results
            start_time: Execution start time
            user_request: Original user request
            
        Returns:
            ProjectResult with execution summary
        """
        end_time = datetime.now(timezone.utc)
        execution_time = (end_time - start_time).total_seconds()
        
        # Calculate statistics
        successful_tasks = sum(1 for result in task_results.values() if result.success)
        failed_tasks = len(task_results) - successful_tasks
        success_rate = (successful_tasks / len(task_results)) * 100 if task_results else 0.0
        
        # Collect artifacts
        all_artifacts = []
        for result in task_results.values():
            if result.success:
                all_artifacts.extend(result.artifacts)
        
        # Create metadata
        metadata = {
            "user_request": user_request,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "total_tasks": len(tasks),
            "task_breakdown": {
                task.type: sum(1 for t in tasks if t.type == task.type)
                for task in tasks
            },
            "config_summary": {
                "max_parallel_tasks": self.config.task_execution.max_parallel_tasks,
                "task_timeout": self.config.task_execution.task_timeout,
                "verification_enabled": self.config.task_execution.verification_enabled
            }
        }
        
        return ProjectResult(
            project_id=project_id,
            success=successful_tasks == len(tasks),
            artifacts=all_artifacts,
            execution_time=execution_time,
            tasks_completed=successful_tasks,
            tasks_failed=failed_tasks,
            success_rate=success_rate,
            metadata=metadata,
            tasks=tasks
        )
    
    async def decompose_request(self, user_request: str) -> Result[List[Task]]:
        """Decompose user request into tasks.
        
        Args:
            user_request: User's request to decompose
            
        Returns:
            Result containing list of tasks or error
        """
        if not self._current_project_id:
            return Result.failure(MetaAgentError("No active project for task decomposition"))
        
        return await self.task_decomposer.decompose_request(user_request, self._current_project_id)
    
    async def coordinate_execution(self, tasks: List[Task], context: TaskContext) -> Result[Dict[str, TaskResult]]:
        """Coordinate execution of tasks.
        
        Args:
            tasks: List of tasks to execute
            context: Task execution context
            
        Returns:
            Result containing task results or error
        """
        return await self.execution_coordinator.coordinate_execution(tasks, context)
    
    async def get_project_info(self, project_id: str) -> Result[Dict[str, Any]]:
        """Get project information.
        
        Args:
            project_id: Project identifier
            
        Returns:
            Result containing project information or error
        """
        return await self.project_manager.get_project_info(project_id)
    
    async def list_projects(self, limit: int = 50) -> Result[List[Dict[str, Any]]]:
        """List all projects.
        
        Args:
            limit: Maximum number of projects to return
            
        Returns:
            Result containing list of projects or error
        """
        return await self.project_manager.list_projects(limit)
    
    async def delete_project(self, project_id: str) -> Result[None]:
        """Delete a project.
        
        Args:
            project_id: Project identifier
            
        Returns:
            Result indicating success or error
        """
        return await self.project_manager.delete_project(project_id)
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """Get execution statistics.
        
        Returns:
            Dictionary of execution statistics
        """
        coordinator_stats = self.execution_coordinator.get_execution_stats()
        
        return {
            "meta_agent": self._execution_stats,
            "task_execution": coordinator_stats,
            "current_project": self._current_project_id
        }
    
    def reset_stats(self) -> None:
        """Reset execution statistics."""
        self._execution_stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_execution_time': 0.0
        }
        self.execution_coordinator.reset_stats()
        
        logger.info("Execution statistics reset")
    
    def update_config(self, config_updates: Dict[str, Any]) -> None:
        """Update configuration.
        
        Args:
            config_updates: Configuration updates to apply
        """
        # Update configuration
        if 'task_execution' in config_updates:
            task_config = config_updates['task_execution']
            if 'max_parallel_tasks' in task_config:
                self.config.task_execution.max_parallel_tasks = task_config['max_parallel_tasks']
            if 'task_timeout' in task_config:
                self.config.task_execution.task_timeout = task_config['task_timeout']
        
        # Update execution coordinator
        self.execution_coordinator.max_parallel_tasks = self.config.task_execution.max_parallel_tasks
        self.execution_coordinator.task_timeout = self.config.task_execution.task_timeout
        
        logger.info("Configuration updated", updates=config_updates)
    
    def clear_caches(self) -> None:
        """Clear all caches."""
        self.task_decomposer.clear_cache()
        self.project_manager.clear_cache()
        
        logger.info("All caches cleared")
    
    async def cleanup(self) -> None:
        """Clean up resources."""
        try:
            # Cleanup execution coordinator
            await self.execution_coordinator.cleanup_agents()
            
            # Close OpenAI client
            if hasattr(self.openai_client, 'close'):
                await self.openai_client.close()
            
            logger.info("MetaAgent cleanup completed")
            
        except Exception as e:
            logger.error("Cleanup failed", error=str(e), exc_info=True)
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.cleanup()


# Backward compatibility alias
MetaAgent = MetaAgentRefactored