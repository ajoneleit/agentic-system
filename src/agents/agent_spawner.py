"""Agent Spawner for MetaAgent modularization.

This module handles spawning and management of sub-agents with different roles.
It provides a clean interface for creating agents and managing their lifecycle.
"""

import asyncio
from typing import Optional
from uuid import UUID

from structlog import get_logger

from src.agents.sub_agent import (
    CodeGeneratorAgent,
    DebugAgent,
    DocumentationAgent,
    RefactorAgent,
    TestWriterAgent,
)
from src.core.coordinator import AgentCoordinator
from src.core.exceptions import AgentSpawnError
from src.core.interfaces import Agent, AgentRole, TaskContext
from src.core.result import Result

logger = get_logger(__name__)


class AgentSpawner:
    """Manages spawning and lifecycle of sub-agents."""

    def __init__(self, coordinator: AgentCoordinator, max_agents: int = 10):
        """Initialize agent spawner.

        Args:
            coordinator: Agent coordinator instance
            max_agents: Maximum number of concurrent agents

        """
        self.coordinator = coordinator
        self.max_agents = max_agents

        # Track active agents
        self._active_agents: dict[UUID, Agent] = {}
        self._agent_roles: dict[UUID, AgentRole] = {}
        self._spawn_lock = asyncio.Lock()

        # Register agent factories
        self._register_agent_factories()

        logger.info("Agent spawner initialized", max_agents=max_agents)

    def _register_agent_factories(self) -> None:
        """Register factories for creating sub-agents."""
        self.coordinator.register_agent_factory(AgentRole.CORE_LOGIC, CodeGeneratorAgent)
        self.coordinator.register_agent_factory(AgentRole.TESTING, TestWriterAgent)
        self.coordinator.register_agent_factory(AgentRole.DOCUMENTATION, DocumentationAgent)
        self.coordinator.register_agent_factory(AgentRole.OPTIMIZATION, RefactorAgent)
        self.coordinator.register_agent_factory(AgentRole.VERIFICATION, DebugAgent)

        logger.debug("Agent factories registered")

    async def spawn_agent(
        self, role: AgentRole, context: TaskContext, metadata: Optional[dict[str, any]] = None
    ) -> Result[Agent]:
        """Spawn a new agent with the specified role.

        Args:
            role: The role for the new agent
            context: Task execution context
            metadata: Optional metadata for the agent

        Returns:
            Result containing the spawned agent or error

        """
        async with self._spawn_lock:
            try:
                # Check agent limit
                if len(self._active_agents) >= self.max_agents:
                    # Try to cleanup idle agents first
                    await self._cleanup_idle_agents()

                    if len(self._active_agents) >= self.max_agents:
                        return Result.failure(
                            AgentSpawnError(f"Maximum agents ({self.max_agents}) reached")
                        )

                # Spawn agent through coordinator
                agent = await self.coordinator.spawn_agent(role, context, metadata or {})

                # Track the agent
                self._active_agents[agent.id] = agent
                self._agent_roles[agent.id] = role

                logger.info(
                    "Agent spawned successfully",
                    agent_id=str(agent.id),
                    role=role.value,
                    active_agents=len(self._active_agents),
                )

                return Result.success(agent)

            except Exception as e:
                logger.error("Failed to spawn agent", role=role.value, error=str(e), exc_info=True)
                return Result.failure(AgentSpawnError(f"Failed to spawn agent: {str(e)}"))

    async def spawn_agents_for_tasks(
        self,
        task_roles: dict[UUID, AgentRole],
        context: TaskContext,
        metadata: Optional[dict[str, any]] = None,
    ) -> Result[dict[UUID, Agent]]:
        """Spawn multiple agents for tasks.

        Args:
            task_roles: Dictionary mapping task IDs to required roles
            context: Task execution context
            metadata: Optional metadata for agents

        Returns:
            Result containing dictionary of task IDs to agents or error

        """
        try:
            agents = {}
            failed_spawns = []

            for task_id, role in task_roles.items():
                spawn_result = await self.spawn_agent(role, context, metadata)

                if spawn_result.is_success():
                    agents[task_id] = spawn_result.value
                else:
                    failed_spawns.append((task_id, spawn_result.error))

            if failed_spawns:
                # Cleanup successfully spawned agents if some failed
                for agent in agents.values():
                    await self.terminate_agent(agent.id)

                error_msg = f"Failed to spawn {len(failed_spawns)} agents"
                return Result.failure(AgentSpawnError(error_msg))

            logger.info(
                "Multiple agents spawned successfully",
                agent_count=len(agents),
                active_agents=len(self._active_agents),
            )

            return Result.success(agents)

        except Exception as e:
            logger.error("Failed to spawn multiple agents", error=str(e))
            return Result.failure(AgentSpawnError(f"Failed to spawn multiple agents: {str(e)}"))

    async def terminate_agent(self, agent_id: UUID) -> Result[None]:
        """Terminate an agent.

        Args:
            agent_id: ID of the agent to terminate

        Returns:
            Result indicating success or error

        """
        try:
            if agent_id not in self._active_agents:
                logger.warning("Attempted to terminate unknown agent", agent_id=str(agent_id))
                return Result.success(None)

            # Terminate through coordinator
            await self.coordinator.terminate_agent(agent_id)

            # Remove from tracking
            self._active_agents.pop(agent_id, None)
            role = self._agent_roles.pop(agent_id, None)

            logger.info(
                "Agent terminated",
                agent_id=str(agent_id),
                role=role.value if role else "unknown",
                active_agents=len(self._active_agents),
            )

            return Result.success(None)

        except Exception as e:
            logger.error("Failed to terminate agent", agent_id=str(agent_id), error=str(e))
            return Result.failure(AgentSpawnError(f"Failed to terminate agent: {str(e)}"))

    async def get_agent_status(self, agent_id: UUID) -> Result[dict[str, any]]:
        """Get status of an agent.

        Args:
            agent_id: ID of the agent

        Returns:
            Result containing agent status or error

        """
        try:
            if agent_id not in self._active_agents:
                return Result.failure(AgentSpawnError(f"Agent not found: {agent_id}"))

            agent = self._active_agents[agent_id]
            status = await agent.report_status()

            return Result.success(status)

        except Exception as e:
            logger.error("Failed to get agent status", agent_id=str(agent_id), error=str(e))
            return Result.failure(AgentSpawnError(f"Failed to get agent status: {str(e)}"))

    async def get_agents_by_role(self, role: AgentRole) -> list[Agent]:
        """Get all active agents with a specific role.

        Args:
            role: The agent role to filter by

        Returns:
            List of agents with the specified role

        """
        return [
            agent
            for agent_id, agent in self._active_agents.items()
            if self._agent_roles.get(agent_id) == role
        ]

    async def _cleanup_idle_agents(self) -> None:
        """Clean up idle agents to free resources."""
        try:
            idle_agents = []

            for agent_id, agent in self._active_agents.items():
                try:
                    status = await agent.report_status()
                    if status.get("status") == "idle" and not status.get("current_task"):
                        idle_agents.append(agent_id)
                except Exception:
                    # If we can't get status, consider it for cleanup
                    idle_agents.append(agent_id)

            # Terminate idle agents
            for agent_id in idle_agents:
                await self.terminate_agent(agent_id)

            if idle_agents:
                logger.info(
                    "Cleaned up idle agents",
                    cleaned_count=len(idle_agents),
                    remaining_agents=len(self._active_agents),
                )

        except Exception as e:
            logger.error("Failed to cleanup idle agents", error=str(e))

    async def terminate_all_agents(self) -> Result[None]:
        """Terminate all active agents.

        Returns:
            Result indicating success or error

        """
        try:
            agent_ids = list(self._active_agents.keys())

            for agent_id in agent_ids:
                await self.terminate_agent(agent_id)

            logger.info("All agents terminated", terminated_count=len(agent_ids))
            return Result.success(None)

        except Exception as e:
            logger.error("Failed to terminate all agents", error=str(e))
            return Result.failure(AgentSpawnError(f"Failed to terminate all agents: {str(e)}"))

    def get_active_agent_count(self) -> int:
        """Get the number of active agents.

        Returns:
            Number of active agents

        """
        return len(self._active_agents)

    def get_active_agents(self) -> dict[UUID, Agent]:
        """Get all active agents.

        Returns:
            Dictionary of active agents

        """
        return self._active_agents.copy()

    def get_agent_distribution(self) -> dict[AgentRole, int]:
        """Get distribution of agents by role.

        Returns:
            Dictionary mapping roles to agent counts

        """
        distribution = {}
        for role in self._agent_roles.values():
            distribution[role] = distribution.get(role, 0) + 1
        return distribution

    def get_spawner_stats(self) -> dict[str, any]:
        """Get spawner statistics.

        Returns:
            Dictionary containing spawner statistics

        """
        return {
            "active_agents": len(self._active_agents),
            "max_agents": self.max_agents,
            "agent_distribution": self.get_agent_distribution(),
            "utilization": (len(self._active_agents) / self.max_agents) * 100,
        }

    async def cleanup(self) -> None:
        """Clean up the agent spawner."""
        try:
            await self.terminate_all_agents()
            logger.info("Agent spawner cleanup completed")
        except Exception as e:
            logger.error("Agent spawner cleanup failed", error=str(e))
