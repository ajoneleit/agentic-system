"""Configuration Manager for MetaAgent modularization.

This module handles settings, dependency injection, and component initialization
for the MetaAgent system. It provides a clean interface for setting up all
required components and managing their configuration.
"""

from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from structlog import get_logger

from config import get_settings
from src.agents.sub_agent import (
    CodeGeneratorAgent,
    DebugAgent,
    DocumentationAgent,
    RefactorAgent,
    TestWriterAgent,
)
from src.core.artifact_manager import ArtifactManager
from src.core.communication import CommunicationHub
from src.core.coordinator import AgentCoordinator
from src.core.dependency_tracker import DependencyTracker
from src.core.failure_analyzer import FailureAnalyzer
from src.core.interfaces import AgentRole
from src.core.task_manager import TaskManager

logger = get_logger(__name__)


class ConfigurationManager:
    """Manages configuration and component initialization for MetaAgent."""

    def __init__(self, artifact_storage_path: Optional[Path] = None):
        """Initialize configuration manager.

        Args:
            artifact_storage_path: Path for artifact storage (defaults to ./projects)

        """
        self.settings = get_settings()
        self.artifact_storage_path = artifact_storage_path or Path("./projects")

        # Initialize state tracking
        self._task_retry_counts: dict[UUID, int] = {}
        self._task_retry_history: dict[UUID, list[dict[str, Any]]] = {}

        logger.info(
            "Configuration manager initialized", artifact_path=str(self.artifact_storage_path)
        )

    def create_ai_client(self):
        """Create and configure the AI client for task decomposition.

        Returns:
            Configured OpenAI client for MetaAgent

        """
        from src.clients.openai_client import OpenAIClient

        ai_client = OpenAIClient()
        logger.info(
            "AI client created for task decomposition",
            model=self.settings.openai.meta_agent_model if self.settings.openai else "o3",
        )
        return ai_client

    def create_task_manager(self) -> TaskManager:
        """Create and configure task manager.

        Returns:
            Configured TaskManager instance

        """
        return TaskManager()

    def create_communication_hub(self) -> CommunicationHub:
        """Create and configure communication hub.

        Returns:
            Configured CommunicationHub instance

        """
        return CommunicationHub()

    def create_agent_coordinator(
        self, task_manager: TaskManager, communication_hub: CommunicationHub
    ) -> AgentCoordinator:
        """Create and configure agent coordinator.

        Args:
            task_manager: Task manager instance
            communication_hub: Communication hub instance

        Returns:
            Configured AgentCoordinator with registered factories

        """
        coordinator = AgentCoordinator(task_manager, communication_hub)

        # Register agent factories
        coordinator.register_agent_factory(AgentRole.CORE_LOGIC, CodeGeneratorAgent)
        coordinator.register_agent_factory(AgentRole.TESTING, TestWriterAgent)
        coordinator.register_agent_factory(AgentRole.DOCUMENTATION, DocumentationAgent)
        coordinator.register_agent_factory(AgentRole.OPTIMIZATION, RefactorAgent)
        coordinator.register_agent_factory(AgentRole.VERIFICATION, DebugAgent)

        logger.info("Agent coordinator created with registered factories")
        return coordinator

    def create_artifact_manager(self) -> ArtifactManager:
        """Create and configure artifact manager.

        Returns:
            Configured ArtifactManager instance

        """
        return ArtifactManager(
            storage_path=self.artifact_storage_path,
            max_memory_cache_size=100,
            enable_compression=True,
            auto_cleanup_days=30,
        )

    def create_dependency_tracker(self) -> DependencyTracker:
        """Create and configure dependency tracker.

        Returns:
            Configured DependencyTracker instance

        """
        return DependencyTracker()

    def create_failure_analyzer(self) -> FailureAnalyzer:
        """Create and configure failure analyzer.

        Returns:
            Configured FailureAnalyzer instance

        """
        return FailureAnalyzer()

    def get_retry_configuration(self) -> dict[str, Any]:
        """Get retry configuration settings.

        Returns:
            Dictionary containing retry configuration

        """
        return {
            "max_retries": self.settings.agent.task_max_retries,
            "retry_delay": self.settings.agent.task_retry_delay,
            "retry_backoff": self.settings.agent.task_retry_backoff,
            "retry_on_verification_failure": self.settings.agent.retry_on_verification_failure,
            "retry_on_api_errors": self.settings.agent.retry_on_api_errors,
            "diagnose_failures": self.settings.agent.diagnose_failures,
        }

    def get_retry_tracking(self) -> tuple[dict[UUID, int], dict[UUID, list[dict[str, Any]]]]:
        """Get retry tracking dictionaries.

        Returns:
            Tuple of (retry_counts, retry_history) dictionaries

        """
        return self._task_retry_counts, self._task_retry_history

    def create_project_paths(self, project_id: Optional[str] = None) -> tuple[Path, Path]:
        """Create project and workspace paths.

        Args:
            project_id: Optional project identifier

        Returns:
            Tuple of (project_path, workspace_path)

        """
        project_name = project_id or "default_project"
        project_path = self.artifact_storage_path / project_name
        workspace_path = project_path / "workspace"

        return project_path, workspace_path

    def create_complete_configuration(self) -> dict[str, Any]:
        """Create complete configuration with all components.

        Returns:
            Dictionary containing all configured components

        """
        # Create core components
        ai_client = self.create_ai_client()
        task_manager = self.create_task_manager()
        communication_hub = self.create_communication_hub()
        coordinator = self.create_agent_coordinator(task_manager, communication_hub)
        artifact_manager = self.create_artifact_manager()
        dependency_tracker = self.create_dependency_tracker()
        failure_analyzer = self.create_failure_analyzer()

        # Get configuration settings
        retry_config = self.get_retry_configuration()
        retry_counts, retry_history = self.get_retry_tracking()
        project_path, workspace_path = self.create_project_paths()

        configuration = {
            # Core components
            "ai_client": ai_client,
            "task_manager": task_manager,
            "communication_hub": communication_hub,
            "coordinator": coordinator,
            "artifact_manager": artifact_manager,
            "dependency_tracker": dependency_tracker,
            "failure_analyzer": failure_analyzer,
            # Configuration settings
            "retry_config": retry_config,
            "retry_counts": retry_counts,
            "retry_history": retry_history,
            # Paths
            "artifact_storage_path": self.artifact_storage_path,
            "project_path": project_path,
            "workspace_path": workspace_path,
            # Settings
            "settings": self.settings,
        }

        logger.info("Complete configuration created with all components")
        return configuration
