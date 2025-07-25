"""Progress Monitor for MetaAgent modularization.

This module handles progress tracking, status reporting, and communication
management for the MetaAgent system. It provides real-time monitoring
of task execution and system health.
"""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from structlog import get_logger

from src.core.communication import CommunicationHub, MessageType
from src.core.coordinator import AgentCoordinator
from src.core.interfaces import Agent, TaskStatus
from src.core.task_manager import TaskManager
from src.prompts.task_decomposition import PROGRESS_AGGREGATION_PROMPT

logger = get_logger(__name__)


class ProgressMonitor:
    """Manages progress tracking and status reporting for MetaAgent."""

    def __init__(
        self,
        task_manager: TaskManager,
        communication_hub: CommunicationHub,
        coordinator: AgentCoordinator,
        ai_client: Any,
    ):
        """Initialize progress monitor.

        Args:
            task_manager: Task manager instance
            communication_hub: Communication hub instance
            coordinator: Agent coordinator instance
            ai_client: AI client for progress analysis

        """
        self.task_manager = task_manager
        self.communication_hub = communication_hub
        self.coordinator = coordinator
        self.ai_client = ai_client

        logger.info("Progress monitor initialized")

    async def register_agent(self, agent: Agent, metadata: dict[str, Any]) -> None:
        """Register an agent with the communication hub.

        Args:
            agent: Agent to register
            metadata: Agent metadata and capabilities

        """
        await self.communication_hub.register_agent(agent, metadata)
        logger.info(
            "Agent registered with communication hub", agent_id=str(agent.id), metadata=metadata
        )

    async def unregister_agent(self, agent_id: UUID) -> None:
        """Unregister an agent from the communication hub.

        Args:
            agent_id: ID of agent to unregister

        """
        await self.communication_hub.unregister_agent(agent_id)
        logger.info("Agent unregistered from communication hub", agent_id=str(agent_id))

    async def get_task_progress(self) -> dict[str, Any]:
        """Get current task execution progress.

        Returns:
            Dictionary containing task progress information

        """
        progress = await self.task_manager.get_progress()

        logger.debug(
            "Task progress retrieved",
            completed=progress.get("completed_tasks", 0),
            total=progress.get("total_tasks", 0),
        )

        return progress

    async def get_system_status(self) -> dict[str, Any]:
        """Get overall system status.

        Returns:
            Dictionary containing system status information

        """
        status = await self.coordinator.get_system_status()

        logger.debug("System status retrieved", status=status)

        return status

    async def check_agent_status(self, agents: dict[UUID, Agent]) -> dict[UUID, dict[str, Any]]:
        """Check status of all active agents.

        Args:
            agents: Dictionary of active agents

        Returns:
            Dictionary mapping agent IDs to their status information

        """
        agent_statuses = {}

        for agent_id, agent in agents.items():
            try:
                status = await agent.report_status()
                agent_statuses[agent_id] = status

                logger.debug(
                    "Agent status checked",
                    agent_id=str(agent_id),
                    status=status.get("status", "unknown"),
                )

            except Exception as e:
                logger.warning("Failed to get agent status", agent_id=str(agent_id), error=str(e))
                agent_statuses[agent_id] = {"status": "error", "error": str(e)}

        return agent_statuses

    async def report_execution_progress(
        self, completed_tasks: int, total_tasks: int, active_agents: int
    ) -> None:
        """Report execution progress with structured logging.

        Args:
            completed_tasks: Number of completed tasks
            total_tasks: Total number of tasks
            active_agents: Number of active agents

        """
        progress_percentage = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

        logger.info(
            "Execution progress",
            completed=completed_tasks,
            total=total_tasks,
            active=active_agents,
            progress_percentage=f"{progress_percentage:.1f}%",
        )

    async def monitor_progress(self) -> dict[str, Any]:
        """Monitor overall system progress with AI analysis.

        Returns:
            Comprehensive progress report with task statuses and metrics

        """
        # Get various progress reports
        task_progress = await self.get_task_progress()
        system_status = await self.get_system_status()

        # Get detailed task information
        all_tasks = await self.task_manager._queue.get_all_tasks()
        active_tasks = [t for t in all_tasks if t.status == TaskStatus.IN_PROGRESS]
        completed_tasks = [t for t in all_tasks if t.status == TaskStatus.COMPLETED]
        failed_tasks = [t for t in all_tasks if t.status == TaskStatus.FAILED]

        # Use AI to aggregate progress analysis
        try:
            prompt = PROGRESS_AGGREGATION_PROMPT.render(
                active_tasks_json=json.dumps([t.model_dump() for t in active_tasks], indent=2),
                completed_tasks_json=json.dumps(
                    [t.model_dump() for t in completed_tasks], indent=2
                ),
                failed_tasks_json=json.dumps([t.model_dump() for t in failed_tasks], indent=2),
                system_status_json=json.dumps(system_status, indent=2),
            )

            from src.utils.async_utils import _await_if_needed

            response = await _await_if_needed(
                self.ai_client.create_message(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=1.0,  # o3 only supports temperature=1
                    max_tokens=500,
                )
            )

            aggregated = response.get("content", "No analysis available")

        except Exception as e:
            logger.warning(f"Failed to get AI progress analysis: {e}")
            aggregated = "AI analysis unavailable"

        progress_report = {
            "task_progress": task_progress,
            "system_status": system_status,
            "aggregated_analysis": aggregated,
            "timestamp": datetime.utcnow().isoformat(),
            "task_breakdown": {
                "active": len(active_tasks),
                "completed": len(completed_tasks),
                "failed": len(failed_tasks),
                "total": len(all_tasks),
            },
        }

        logger.info(
            "Progress monitoring complete",
            active_tasks=len(active_tasks),
            completed_tasks=len(completed_tasks),
            failed_tasks=len(failed_tasks),
        )

        return progress_report

    async def handle_task_completion(
        self, task_id: UUID, agent_id: UUID, success: bool, execution_time: float
    ) -> None:
        """Handle task completion reporting.

        Args:
            task_id: ID of completed task
            agent_id: ID of agent that completed the task
            success: Whether task completed successfully
            execution_time: Task execution time in seconds

        """
        await self.coordinator.handle_task_completion(agent_id, task_id, success, execution_time)

        logger.info(
            "Task completion handled",
            task_id=str(task_id),
            agent_id=str(agent_id),
            success=success,
            execution_time=execution_time,
        )

    async def collect_agent_artifacts(
        self, agent_statuses: dict[UUID, dict[str, Any]]
    ) -> list[UUID]:
        """Collect artifact IDs from agent status reports.

        Args:
            agent_statuses: Dictionary of agent status information

        Returns:
            List of artifact UUIDs

        """
        artifacts = []

        for agent_id, status in agent_statuses.items():
            if "produced_artifacts" in status:
                for aid in status["produced_artifacts"]:
                    try:
                        artifacts.append(UUID(aid))
                    except ValueError as e:
                        logger.warning(
                            "Invalid artifact UUID from agent",
                            agent_id=str(agent_id),
                            artifact_id=aid,
                            error=str(e),
                        )

        logger.debug(f"Collected {len(artifacts)} artifacts from agent reports")
        return artifacts

    async def send_progress_message(
        self, recipient_id: UUID, message_type: MessageType, content: dict[str, Any]
    ) -> None:
        """Send progress message via communication hub.

        Args:
            recipient_id: ID of message recipient
            message_type: Type of message to send
            content: Message content

        """
        try:
            await self.communication_hub.send_message(recipient_id, message_type, content)

            logger.debug(
                "Progress message sent", recipient=str(recipient_id), type=message_type.value
            )

        except Exception as e:
            logger.error(
                "Failed to send progress message",
                recipient=str(recipient_id),
                type=message_type.value,
                error=str(e),
            )

    def get_progress_metrics(self) -> dict[str, Any]:
        """Get basic progress metrics.

        Returns:
            Dictionary containing progress metrics

        """
        return {
            "monitoring_active": True,
            "last_update": datetime.utcnow().isoformat(),
            "communication_hub_status": "active" if self.communication_hub else "inactive",
            "task_manager_status": "active" if self.task_manager else "inactive",
            "coordinator_status": "active" if self.coordinator else "inactive",
        }
