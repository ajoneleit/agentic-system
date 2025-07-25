"""Refactored Meta Agent implementation.

This is a cleaner, more maintainable version of the MetaAgent that uses
extracted components for better separation of concerns.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from structlog import get_logger

from src.agents.agent_spawner import AgentSpawner
from src.agents.configuration_manager import ConfigurationManager
from src.agents.error_handler import ErrorHandler
from src.agents.execution_coordinator import ExecutionCoordinator
from src.agents.meta_agent_config import MetaAgentConfig, load_config
from src.agents.progress_monitor import ProgressMonitor
from src.agents.project_manager import ProjectManager
from src.agents.result_processor import ResultProcessor
from src.agents.task_decomposer import TaskDecomposer
from src.core.exceptions import MetaAgentError
from src.core.interfaces import Agent, AgentRole, Artifact, MetaAgentInterface, Task, TaskContext
from src.core.result import Result
from src.core.task_result import TaskResult
from src.utils.app_logging import log_execution_time

logger = get_logger(__name__)


@dataclass
class ProjectResult:
    """Result of processing a user request."""

    project_id: str = ""
    success: bool = True
    artifacts: list[Artifact] = field(default_factory=list)
    execution_time: float = 0.0
    tasks_completed: int = 0
    tasks_failed: int = 0
    success_rate: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    tasks: list[Task] = field(default_factory=list)

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

    def __init__(
        self, config: Optional[MetaAgentConfig] = None, artifact_storage_path: Optional[Path] = None
    ):
        """Initialize the refactored Meta Agent.

        Args:
            config: Optional configuration, loads default if not provided
            artifact_storage_path: Optional path for artifact storage (for backward compatibility)

        """
        super().__init__()

        # Load configuration
        self.config = config or load_config()
        validation_errors = self.config.validate()
        if validation_errors:
            raise MetaAgentError(f"Configuration validation failed: {validation_errors}")

        # Initialize configuration manager for centralized component setup
        self.config_manager = ConfigurationManager(
            artifact_storage_path=artifact_storage_path or self.config.project.artifact_storage_path
        )

        # Create all components using configuration manager
        components = self.config_manager.create_complete_configuration()

        # Assign components
        self.ai_client = components["ai_client"]
        self.task_manager = components["task_manager"]
        self.communication_hub = components["communication_hub"]
        self.coordinator = components["coordinator"]
        self.artifact_manager = components["artifact_manager"]
        self.dependency_tracker = components["dependency_tracker"]
        self.failure_analyzer = components["failure_analyzer"]

        # Initialize specialized components with dependencies
        self.error_handler = ErrorHandler(
            failure_analyzer=self.failure_analyzer,
            task_manager=self.task_manager,
            **components["retry_config"],
        )

        self.progress_monitor = ProgressMonitor(
            task_manager=self.task_manager,
            communication_hub=self.communication_hub,
            coordinator=self.coordinator,
            ai_client=self.ai_client,
        )

        self.agent_spawner = AgentSpawner(
            coordinator=self.coordinator, max_agents=self.config.agent.max_active_agents
        )

        self.result_processor = ResultProcessor(artifact_manager=self.artifact_manager)

        # Initialize higher-level components
        self.task_decomposer = TaskDecomposer(self.ai_client)
        self.project_manager = ProjectManager(
            base_storage_path=self.config.project.base_storage_path,
            artifact_manager=self.artifact_manager,
        )
        self.execution_coordinator = ExecutionCoordinator(
            max_parallel_tasks=self.config.task_execution.max_parallel_tasks,
            task_timeout=self.config.task_execution.task_timeout,
        )

        # Runtime state
        self._current_project_id: Optional[str] = None
        self._execution_stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_execution_time": 0.0,
        }

        logger.info(
            "MetaAgent initialized with fully modular architecture",
            max_parallel_tasks=self.config.task_execution.max_parallel_tasks,
            max_agents=self.config.agent.max_active_agents,
            components_loaded=len(
                [
                    "configuration_manager",
                    "error_handler",
                    "progress_monitor",
                    "agent_spawner",
                    "result_processor",
                    "task_decomposer",
                    "project_manager",
                    "execution_coordinator",
                ]
            ),
        )

    async def initialize(self, context: Optional[TaskContext] = None) -> None:
        """Initialize the Meta Agent with context.

        Args:
            context: Optional execution context

        """
        # Start coordinator
        await self.coordinator.start()

        # Register self with communication hub
        await self.progress_monitor.register_agent(
            self,
            {
                "role": "orchestrator",
                "capabilities": ["task_decomposition", "agent_spawning", "coordination"],
                "version": "refactored",
                "components": [
                    "configuration_manager",
                    "error_handler",
                    "progress_monitor",
                    "agent_spawner",
                    "result_processor",
                    "task_decomposer",
                    "project_manager",
                    "execution_coordinator",
                ],
            },
        )

        logger.info("MetaAgent fully initialized with all modular components")

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
                timestamp=start_time.isoformat(),
            )

            # Phase 1: Initialize project storage
            project_init_result = await self.project_manager.initialize_project_storage(
                user_request
            )
            if project_init_result.is_failure():
                return Result.failure(project_init_result.get_error())

            project_id = project_init_result.unwrap()
            self._current_project_id = project_id

            # Phase 2: Decompose request into tasks
            decomposition_result = await self.task_decomposer.decompose_request(
                user_request, project_id
            )
            if decomposition_result.is_failure():
                return Result.failure(decomposition_result.get_error())

            tasks = decomposition_result.unwrap()

            # Phase 3: Create execution context
            context = await self._create_execution_context(project_id, user_request, tasks)

            # Phase 4: Execute tasks
            execution_result = await self.execution_coordinator.coordinate_execution(tasks, context)
            if execution_result.is_failure():
                return Result.failure(execution_result.get_error())

            task_results = execution_result.unwrap()

            # Phase 5: Store execution artifacts
            storage_result = await self.project_manager.store_execution_artifacts(
                project_id, task_results
            )
            if storage_result.is_failure():
                logger.warning(
                    "Failed to store execution artifacts", error=storage_result.get_error()
                )

            # Phase 6: Create project manifest
            manifest_result = await self.project_manager.create_project_manifest(
                user_request, task_results
            )
            if manifest_result.is_failure():
                logger.warning(
                    "Failed to create project manifest", error=manifest_result.get_error()
                )

            # Phase 7: Process and aggregate results
            processing_result = await self.result_processor.generate_execution_report(
                task_results, tasks, project_id, user_request, start_time
            )
            if processing_result.is_failure():
                logger.warning(
                    "Failed to generate execution report", error=processing_result.get_error()
                )
                processing_report = {}
            else:
                processing_report = processing_result.unwrap()

            # Phase 8: Generate final result
            project_result = await self._create_project_result(
                project_id, tasks, task_results, start_time, user_request, processing_report
            )

            # Update statistics
            self._execution_stats["total_requests"] += 1
            if project_result.success:
                self._execution_stats["successful_requests"] += 1
            else:
                self._execution_stats["failed_requests"] += 1
            self._execution_stats["total_execution_time"] += project_result.execution_time

            logger.info(
                "Request processing completed",
                project_id=project_id,
                success=project_result.success,
                execution_time=project_result.execution_time,
                tasks_completed=project_result.tasks_completed,
                tasks_failed=project_result.tasks_failed,
            )

            return Result.success(project_result)

        except Exception as e:
            logger.error("Request processing failed", error=str(e), exc_info=True)
            self._execution_stats["failed_requests"] += 1
            return Result.failure(MetaAgentError(f"Failed to process request: {str(e)}"))

    async def _create_execution_context(
        self, project_id: str, user_request: str, tasks: list[Task]
    ) -> TaskContext:
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
                "task_count": len(tasks),
            },
            parent_task_id=None,
            sibling_task_ids={t.id for t in tasks},
            artifact_manager=self.artifact_manager,
            project_id=project_id,
            artifact_metadata_template={
                "project_id": project_id,
                "request": user_request[:200],
                "created_by": "agentic_system",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            artifact_naming_convention="{name}",
            enable_artifact_caching=self.config.enable_caching,
            auto_version_on_change=True,
            link_test_artifacts=True,
        )

        return context

    async def _create_project_result(
        self,
        project_id: str,
        tasks: list[Task],
        task_results: dict[str, TaskResult],
        start_time: datetime,
        user_request: str,
        processing_report: Optional[dict[str, Any]] = None,
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
        successful_tasks = sum(
            1 for result in task_results.values() if result.is_success() and result.unwrap().success
        )
        failed_tasks = len(task_results) - successful_tasks
        success_rate = (successful_tasks / len(task_results)) * 100 if task_results else 0.0

        # Collect artifacts
        all_artifacts = []
        for result in task_results.values():
            if result.is_success():
                task_result = result.unwrap()
                if task_result.success:
                    all_artifacts.extend(task_result.artifacts)

        # Create metadata
        metadata = {
            "user_request": user_request,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "total_tasks": len(tasks),
            "task_breakdown": {
                task.required_role.value if task.required_role else "general": sum(
                    1
                    for t in tasks
                    if (t.required_role.value if t.required_role else "general")
                    == (task.required_role.value if task.required_role else "general")
                )
                for task in tasks
            },
            "config_summary": {
                "max_parallel_tasks": self.config.task_execution.max_parallel_tasks,
                "task_timeout": self.config.task_execution.task_timeout,
                "verification_enabled": self.config.task_execution.verification_enabled,
            },
        }

        # Include processing report if available
        if processing_report:
            metadata["execution_report"] = processing_report

        return ProjectResult(
            project_id=project_id,
            success=successful_tasks == len(tasks),
            artifacts=all_artifacts,
            execution_time=execution_time,
            tasks_completed=successful_tasks,
            tasks_failed=failed_tasks,
            success_rate=success_rate,
            metadata=metadata,
            tasks=tasks,
        )

    async def decompose_request(self, user_request: str) -> Result[list[Task]]:
        """Decompose user request into tasks.

        Args:
            user_request: User's request to decompose

        Returns:
            Result containing list of tasks or error

        """
        if not self._current_project_id:
            return Result.failure(MetaAgentError("No active project for task decomposition"))

        return await self.task_decomposer.decompose_request(user_request, self._current_project_id)

    async def coordinate_execution(
        self, tasks: list[Task], context: TaskContext
    ) -> Result[dict[str, TaskResult]]:
        """Coordinate execution of tasks.

        Args:
            tasks: List of tasks to execute
            context: Task execution context

        Returns:
            Result containing task results or error

        """
        return await self.execution_coordinator.coordinate_execution(tasks, context)

    async def get_project_info(self, project_id: str) -> Result[dict[str, Any]]:
        """Get project information.

        Args:
            project_id: Project identifier

        Returns:
            Result containing project information or error

        """
        return await self.project_manager.get_project_info(project_id)

    async def list_projects(self, limit: int = 50) -> Result[list[dict[str, Any]]]:
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

    def get_execution_stats(self) -> dict[str, Any]:
        """Get comprehensive execution statistics from all components.

        Returns:
            Dictionary of execution statistics

        """
        try:
            coordinator_stats = self.execution_coordinator.get_execution_stats()
            spawner_stats = self.agent_spawner.get_spawner_stats()
            processing_stats = self.result_processor.get_processing_stats()
            error_stats = self.error_handler.get_retry_statistics()
            progress_stats = self.progress_monitor.get_progress_metrics()

            return {
                "meta_agent": self._execution_stats,
                "task_execution": coordinator_stats,
                "agent_spawning": spawner_stats,
                "result_processing": processing_stats,
                "error_handling": error_stats,
                "progress_monitoring": progress_stats,
                "current_project": self._current_project_id,
                "modular_components": {
                    "configuration_manager": True,
                    "error_handler": True,
                    "progress_monitor": True,
                    "agent_spawner": True,
                    "result_processor": True,
                    "task_decomposer": True,
                    "project_manager": True,
                    "execution_coordinator": True,
                },
            }
        except Exception as e:
            logger.error("Failed to gather comprehensive stats", error=str(e))
            return {
                "meta_agent": self._execution_stats,
                "current_project": self._current_project_id,
                "stats_error": str(e),
            }

    def reset_stats(self) -> None:
        """Reset execution statistics for all components."""
        self._execution_stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_execution_time": 0.0,
        }

        # Reset all component statistics
        try:
            self.execution_coordinator.reset_stats()
            self.result_processor.reset_stats()
            # Note: Other components may not have reset_stats methods

            logger.info("All execution statistics reset")
        except Exception as e:
            logger.warning("Some statistics could not be reset", error=str(e))

    def update_config(self, config_updates: dict[str, Any]) -> None:
        """Update configuration.

        Args:
            config_updates: Configuration updates to apply

        """
        # Update configuration
        if "task_execution" in config_updates:
            task_config = config_updates["task_execution"]
            if "max_parallel_tasks" in task_config:
                self.config.task_execution.max_parallel_tasks = task_config["max_parallel_tasks"]
            if "task_timeout" in task_config:
                self.config.task_execution.task_timeout = task_config["task_timeout"]

        # Update execution coordinator
        self.execution_coordinator.max_parallel_tasks = (
            self.config.task_execution.max_parallel_tasks
        )
        self.execution_coordinator.task_timeout = self.config.task_execution.task_timeout

        logger.info("Configuration updated", updates=config_updates)

    def clear_caches(self) -> None:
        """Clear all caches."""
        self.task_decomposer.clear_cache()
        self.project_manager.clear_cache()

        logger.info("All caches cleared")

    async def get_health_status(self) -> dict[str, Any]:
        """Get health status of all modular components.

        Returns:
            Dictionary containing health status of all components

        """
        health_status = {
            "overall_status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {},
        }

        try:
            # Check core components
            health_status["components"]["configuration_manager"] = {
                "status": "healthy",
                "settings_loaded": bool(self.config_manager),
                "storage_path": str(self.config.project.artifact_storage_path),
            }

            health_status["components"]["task_manager"] = {
                "status": "healthy",
                "initialized": bool(self.task_manager),
            }

            health_status["components"]["agent_spawner"] = {
                "status": "healthy",
                "active_agents": self.agent_spawner.get_active_agent_count(),
                "max_agents": self.agent_spawner.max_agents,
            }

            health_status["components"]["execution_coordinator"] = {
                "status": "healthy",
                "max_parallel_tasks": self.execution_coordinator.max_parallel_tasks,
            }

            health_status["components"]["result_processor"] = {
                "status": "healthy",
                "results_processed": self.result_processor.get_processing_stats()[
                    "results_processed"
                ],
            }

            # Check AI client
            health_status["components"]["ai_client"] = {
                "status": "healthy" if self.ai_client else "unavailable",
                "model": getattr(self.config, "openai_model", "unknown"),
            }

            # Check artifact manager
            health_status["components"]["artifact_manager"] = {
                "status": "healthy" if self.artifact_manager else "unavailable",
                "storage_path": str(self.config.project.artifact_storage_path),
            }

            health_status["overall_status"] = "healthy"

        except Exception as e:
            logger.error("Health check failed", error=str(e))
            health_status["overall_status"] = "degraded"
            health_status["error"] = str(e)

        return health_status

    # ===============================================
    # Abstract Method Implementations (ZEN HARMONY)
    # ===============================================

    async def decompose_task(self, user_prompt: str) -> list[Task]:
        """Decompose user prompt into executable tasks using TaskDecomposer.

        Args:
            user_prompt: User's request in natural language

        Returns:
            List of executable tasks with proper dependencies

        """
        try:
            # Use modular TaskDecomposer component
            decomposition_result = await self.task_decomposer.decompose_request(
                user_prompt, self._current_project_id or "default"
            )

            if decomposition_result.is_failure():
                logger.error("Task decomposition failed", error=decomposition_result.get_error())
                return []

            return decomposition_result.unwrap()

        except Exception as e:
            logger.error("Task decomposition error", error=str(e))
            return []

    async def spawn_agent(self, role: AgentRole) -> Agent:
        """Spawn a new sub-agent using AgentSpawner.

        Args:
            role: Role for the new agent

        Returns:
            Newly created and initialized agent instance

        """
        try:
            # Use modular AgentSpawner component
            spawn_result = await self.agent_spawner.spawn_agent(role)

            if spawn_result.is_failure():
                logger.error("Agent spawning failed", role=role, error=spawn_result.get_error())
                raise MetaAgentError(f"Failed to spawn {role} agent: {spawn_result.get_error()}")

            return spawn_result.unwrap()

        except Exception as e:
            logger.error("Agent spawning error", role=role, error=str(e))
            raise MetaAgentError(f"Failed to spawn {role} agent: {str(e)}")

    async def monitor_progress(self) -> dict[str, Any]:
        """Monitor overall system progress using ProgressMonitor.

        Returns:
            Dictionary with system progress and performance metrics

        """
        try:
            # Use modular ProgressMonitor component
            return await self.progress_monitor.get_system_status()

        except Exception as e:
            logger.error("Progress monitoring error", error=str(e))
            return {"status": "error", "error": str(e), "active_tasks": 0, "completed_tasks": 0}

    async def aggregate_results(self, task_results: dict[UUID, list[Artifact]]) -> ProjectResult:
        """Aggregate task results using ResultProcessor.

        Args:
            task_results: Dictionary mapping task IDs to artifacts

        Returns:
            Aggregated project result

        """
        try:
            # Use modular ResultProcessor component
            aggregation_result = await self.result_processor.aggregate_task_results(task_results)

            if aggregation_result.is_failure():
                logger.error("Result aggregation failed", error=aggregation_result.get_error())
                return ProjectResult(
                    success=False, metadata={"error": str(aggregation_result.get_error())}
                )

            return aggregation_result.unwrap()

        except Exception as e:
            logger.error("Result aggregation error", error=str(e))
            return ProjectResult(success=False, metadata={"error": str(e)})

    async def handle_failure(self, task: Task, error: str) -> list[Task]:
        """Handle task failure using ErrorHandler.

        Args:
            task: Failed task
            error: Error message

        Returns:
            List of repair tasks (if any)

        """
        try:
            # Use modular ErrorHandler component
            failure_result = await self.error_handler.handle_task_failure(task, Exception(error))

            if failure_result.is_failure():
                logger.error(
                    "Failure handling failed", task_id=task.id, error=failure_result.get_error()
                )
                return []

            return failure_result.unwrap()

        except Exception as e:
            logger.error("Failure handling error", task_id=task.id, error=str(e))
            return []

    async def shutdown(self) -> None:
        """Gracefully shutdown using cleanup method."""
        await self.cleanup()

    async def cleanup(self) -> None:
        """Clean up resources."""
        try:
            # Cleanup all modular components
            cleanup_tasks = []

            # Cleanup execution coordinator
            cleanup_tasks.append(self.execution_coordinator.cleanup_agents())

            # Cleanup agent spawner
            cleanup_tasks.append(self.agent_spawner.cleanup())

            # Cleanup coordinator
            cleanup_tasks.append(self.coordinator.stop())

            # Unregister from communication hub
            cleanup_tasks.append(self.progress_monitor.unregister_agent(self.id))

            # Execute all cleanup tasks
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)

            # Close AI client
            if hasattr(self.ai_client, "close"):
                await self.ai_client.close()

            logger.info("MetaAgent cleanup completed for all modular components")

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
