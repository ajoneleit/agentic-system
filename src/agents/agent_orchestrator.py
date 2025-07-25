"""Agent Orchestrator for MetaAgent modularization.

This module handles agent spawning, coordination, and execution management
for the MetaAgent system. It orchestrates sub-agents to execute tasks
in the correct order with proper dependency handling.
"""

import asyncio
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from structlog import get_logger

from src.core.agent_errors import AgentSpawnError, OrchestrationError
from src.core.coordinator import AgentCoordinator
from src.core.exceptions import TaskError
from src.core.interfaces import Agent, AgentRole, Task, TaskContext
from src.core.result import Result
from src.core.task_manager import TaskManager
from src.core.task_result import TaskResult

logger = get_logger(__name__)


class AgentOrchestrator:
    """Manages agent spawning and task execution coordination for MetaAgent."""

    def __init__(
        self,
        coordinator: AgentCoordinator,
        task_manager: TaskManager,
        max_concurrent_agents: int = 5,
    ):
        """Initialize agent orchestrator.

        Args:
            coordinator: Agent coordinator instance
            task_manager: Task manager instance
            max_concurrent_agents: Maximum number of concurrent agents

        """
        self.coordinator = coordinator
        self.task_manager = task_manager
        self.max_concurrent_agents = max_concurrent_agents

        # Track active agents and task execution
        self._active_agents: dict[UUID, Agent] = {}
        self._task_results: dict[UUID, TaskResult] = {}

        logger.info("Agent orchestrator initialized", max_concurrent=max_concurrent_agents)

    async def coordinate_execution(
        self, tasks: list[Task], context: TaskContext
    ) -> Result[dict[UUID, TaskResult]]:
        """Coordinate the execution of tasks by managing agents.

        This method handles the core orchestration logic including:
        - Dependency resolution and task ordering
        - Agent spawning and lifecycle management
        - Parallel execution within dependency constraints
        - Error handling and retry coordination

        Args:
            tasks: List of tasks to execute
            context: Execution context

        Returns:
            Result containing task results mapping or error

        """
        try:
            logger.info(f"Starting coordinated execution of {len(tasks)} tasks")

            # Reset execution state
            self._task_results.clear()
            self._active_agents.clear()

            # Execute tasks with dependency management
            await self._execute_tasks_with_dependencies(tasks, context)

            # Validate all tasks completed
            if len(self._task_results) != len(tasks):
                incomplete_tasks = [t for t in tasks if t.id not in self._task_results]
                logger.warning(
                    f"Not all tasks completed. Missing {len(incomplete_tasks)} tasks",
                    incomplete_task_names=[t.name for t in incomplete_tasks],
                )

            logger.info(
                "Coordinated execution completed",
                total_tasks=len(tasks),
                completed_tasks=len(self._task_results),
                successful_tasks=sum(1 for r in self._task_results.values() if r.success),
            )

            return Result.success(self._task_results)

        except Exception as e:
            logger.error("Task coordination failed", error=str(e), exc_info=True)
            return Result.failure(
                OrchestrationError(
                    message=f"Task coordination failed: {str(e)}",
                    agent_id=UUID(
                        "00000000-0000-0000-0000-000000000000"
                    ),  # MetaAgent ID placeholder
                    details={"task_count": len(tasks)},
                )
            )

    async def _execute_tasks_with_dependencies(
        self, tasks: list[Task], context: TaskContext
    ) -> None:
        """Execute tasks respecting dependencies and concurrency limits.

        Args:
            tasks: List of tasks to execute
            context: Execution context

        """
        completed_tasks: set[UUID] = set()
        failed_tasks: set[UUID] = set()

        # Main execution loop
        while len(completed_tasks) + len(failed_tasks) < len(tasks):
            # Find tasks ready for execution
            ready_tasks = self._get_ready_tasks(tasks, completed_tasks, failed_tasks)

            # Check for deadlock
            if not ready_tasks and len(self._active_agents) == 0:
                # Handle potential deadlock
                blocked_tasks = [
                    t for t in tasks if t.id not in completed_tasks and t.id not in failed_tasks
                ]

                if blocked_tasks:
                    await self._handle_deadlock(blocked_tasks, failed_tasks, tasks, context)
                    continue
                else:
                    break

            # Spawn agents for ready tasks (respecting concurrency limits)
            await self._spawn_agents_for_ready_tasks(
                ready_tasks, context, completed_tasks, failed_tasks
            )

            # Monitor and collect completed agents
            if self._active_agents:
                await self._monitor_active_agents(completed_tasks, failed_tasks)
            else:
                # Brief pause if no active agents to prevent tight loop
                await asyncio.sleep(0.1)

            # Report progress
            await self._report_execution_progress(
                len(completed_tasks), len(tasks), len(self._active_agents)
            )

    def _get_ready_tasks(
        self, all_tasks: list[Task], completed_tasks: set[UUID], failed_tasks: set[UUID]
    ) -> list[Task]:
        """Get tasks that are ready for execution.

        Args:
            all_tasks: All tasks in the execution
            completed_tasks: Set of completed task IDs
            failed_tasks: Set of failed task IDs

        Returns:
            List of tasks ready for execution

        """
        ready_tasks = []

        for task in all_tasks:
            # Skip if already processed
            if task.id in completed_tasks or task.id in failed_tasks:
                continue

            # Skip if already being executed
            if any(agent.current_task_id == task.id for agent in self._active_agents.values()):
                continue

            # Check if all dependencies are satisfied
            dependencies_satisfied = all(dep_id in completed_tasks for dep_id in task.dependencies)

            if dependencies_satisfied:
                ready_tasks.append(task)

        return ready_tasks

    async def _spawn_agents_for_ready_tasks(
        self,
        ready_tasks: list[Task],
        context: TaskContext,
        completed_tasks: set[UUID],
        failed_tasks: set[UUID],
    ) -> None:
        """Spawn agents for ready tasks within concurrency limits.

        Args:
            ready_tasks: Tasks ready for execution
            context: Execution context
            completed_tasks: Set of completed task IDs
            failed_tasks: Set of failed task IDs

        """
        # Respect concurrency limits
        available_slots = self.max_concurrent_agents - len(self._active_agents)
        tasks_to_spawn = ready_tasks[:available_slots]

        for task in tasks_to_spawn:
            try:
                # Spawn agent for this task
                agent = await self.spawn_agent(task.required_role or AgentRole.CORE_LOGIC, context)
                self._active_agents[agent.id] = agent

                # Start task execution asynchronously
                asyncio.create_task(
                    self._execute_task_with_agent(
                        task, agent, context, completed_tasks, failed_tasks
                    )
                )

                logger.info(
                    "Agent spawned for task",
                    task_id=str(task.id),
                    task_name=task.name,
                    agent_id=str(agent.id),
                    active_agents=len(self._active_agents),
                )

            except Exception as e:
                logger.error(
                    "Failed to spawn agent for task",
                    task_id=str(task.id),
                    task_name=task.name,
                    error=str(e),
                )

                # Mark task as failed
                failed_tasks.add(task.id)
                await self.task_manager.fail_task(task.id, str(e))

                # Create error task result
                error_result = TaskResult(
                    task_id=task.id,
                    agent_id=UUID("00000000-0000-0000-0000-000000000000"),
                    success=False,
                )
                error_result.add_error(f"Failed to spawn agent: {str(e)}")
                self._task_results[task.id] = error_result

    async def _execute_task_with_agent(
        self,
        task: Task,
        agent: Agent,
        context: TaskContext,
        completed_tasks: set[UUID],
        failed_tasks: set[UUID],
    ) -> None:
        """Execute a single task with an agent.

        Args:
            task: Task to execute
            agent: Agent to execute the task
            context: Execution context
            completed_tasks: Set of completed task IDs to update
            failed_tasks: Set of failed task IDs to update

        """
        try:
            # Update context with current state
            context.completed_tasks = completed_tasks.copy()

            # Start task execution
            await self.task_manager.start_task(task.id)
            task_result = await agent.execute_task(task, context)

            # Store result
            self._task_results[task.id] = task_result

            # Update task status
            if task_result.success:
                await self.task_manager.complete_task(task.id, task_result.artifacts)
                completed_tasks.add(task.id)

                logger.info(
                    "Task completed successfully",
                    task_id=str(task.id),
                    task_name=task.name,
                    agent_id=str(agent.id),
                )
            else:
                error_msg = "; ".join(task_result.errors) if task_result.errors else "Task failed"
                await self.task_manager.fail_task(task.id, error_msg)
                failed_tasks.add(task.id)

                logger.error(
                    "Task failed",
                    task_id=str(task.id),
                    task_name=task.name,
                    agent_id=str(agent.id),
                    error=error_msg,
                )

        except Exception as e:
            logger.error(
                "Task execution exception",
                task_id=str(task.id),
                task_name=task.name,
                agent_id=str(agent.id),
                error=str(e),
            )

            # Mark as failed
            failed_tasks.add(task.id)
            await self.task_manager.fail_task(task.id, str(e))

            # Create error result
            error_result = TaskResult(
                task_id=task.id,
                agent_id=agent.id,
                success=False,
            )
            error_result.add_error(f"Execution exception: {str(e)}")
            self._task_results[task.id] = error_result

        finally:
            # Clean up agent
            if agent.id in self._active_agents:
                del self._active_agents[agent.id]

            try:
                await self.coordinator.terminate_agent(agent.id)
            except Exception as e:
                logger.warning(f"Failed to terminate agent {agent.id}: {e}")

    async def _monitor_active_agents(
        self, completed_tasks: set[UUID], failed_tasks: set[UUID]
    ) -> None:
        """Monitor active agents and collect completed ones.

        Args:
            completed_tasks: Set of completed task IDs to update
            failed_tasks: Set of failed task IDs to update

        """
        # Check agent status (agents are removed in _execute_task_with_agent)
        await asyncio.sleep(1)  # Poll interval

        # Log current status
        if self._active_agents:
            logger.debug(
                f"Monitoring {len(self._active_agents)} active agents",
                active_agent_ids=[str(aid) for aid in self._active_agents.keys()],
            )

    async def _handle_deadlock(
        self,
        blocked_tasks: list[Task],
        failed_tasks: set[UUID],
        all_tasks: list[Task],
        context: TaskContext,
    ) -> None:
        """Handle potential deadlock by analyzing blocked tasks.

        Args:
            blocked_tasks: Tasks that are blocked
            failed_tasks: Set of failed task IDs
            all_tasks: All tasks in execution
            context: Execution context

        """
        logger.warning(
            "Potential deadlock detected",
            blocked_count=len(blocked_tasks),
            blocked_tasks=[t.name for t in blocked_tasks],
            failed_count=len(failed_tasks),
        )

        # Check if blocked tasks have failed dependencies
        can_skip = []
        truly_deadlocked = []

        for task in blocked_tasks:
            has_failed_dep = any(dep_id in failed_tasks for dep_id in task.dependencies)

            if has_failed_dep:
                can_skip.append(task)
            else:
                # Check for invalid dependencies
                all_task_ids = {t.id for t in all_tasks}
                invalid_deps = [d for d in task.dependencies if d not in all_task_ids]

                if invalid_deps:
                    logger.warning(
                        f"Task {task.name} has invalid dependencies",
                        invalid_deps=[str(d) for d in invalid_deps],
                    )
                    can_skip.append(task)
                else:
                    truly_deadlocked.append(task)

        # Skip tasks with failed dependencies
        for task in can_skip:
            logger.warning(
                f"Skipping task {task.name} due to failed dependencies", task_id=str(task.id)
            )
            await self.task_manager.fail_task(task.id, "Skipped due to failed dependencies")
            failed_tasks.add(task.id)

            # Create failed result
            failed_result = TaskResult(
                task_id=task.id,
                agent_id=UUID("00000000-0000-0000-0000-000000000000"),
                success=False,
            )
            failed_result.add_error("Task skipped due to failed dependencies")
            self._task_results[task.id] = failed_result

        # If we still have truly deadlocked tasks, raise error
        if truly_deadlocked and not can_skip:
            logger.error(
                "True deadlock detected",
                blocked_count=len(truly_deadlocked),
                blocked_tasks=[t.name for t in truly_deadlocked],
            )
            raise TaskError(
                truly_deadlocked[0].id, "Task execution deadlocked - circular dependencies detected"
            )

    async def spawn_agent(self, role: AgentRole, context: Optional[TaskContext] = None) -> Agent:
        """Spawn a new sub-agent with specified role.

        Args:
            role: Role for the new agent
            context: Optional execution context

        Returns:
            Newly created agent instance

        """
        agent = await self.coordinator.spawn_agent(
            role,
            context or TaskContext(project_root="/tmp"),
            metadata={
                "spawned_by": "agent_orchestrator",
                "spawn_time": datetime.utcnow().isoformat(),
            },
        )

        logger.info(
            "Spawned sub-agent",
            agent_id=str(agent.id),
            role=role.value,
        )

        return agent

    async def spawn_agents_for_tasks(
        self, tasks: list[Task], context: TaskContext
    ) -> Result[dict[UUID, Agent]]:
        """Spawn agents for multiple tasks.

        Args:
            tasks: List of tasks requiring agents
            context: Execution context

        Returns:
            Result containing mapping of agent IDs to agents or error

        """
        try:
            agents = {}
            for task in tasks:
                agent = await self.spawn_agent(task.required_role or AgentRole.CORE_LOGIC, context)
                agents[agent.id] = agent
            return Result.success(agents)
        except Exception as e:
            return Result.failure(
                AgentSpawnError(
                    message=f"Failed to spawn agents: {str(e)}",
                    agent_id=UUID("00000000-0000-0000-0000-000000000000"),
                    details={"task_count": len(tasks)},
                )
            )

    async def _report_execution_progress(self, completed: int, total: int, active: int) -> None:
        """Report execution progress.

        Args:
            completed: Number of completed tasks
            total: Total number of tasks
            active: Number of active agents

        """
        progress_percentage = (completed / total * 100) if total > 0 else 0

        logger.info(
            "Execution progress",
            completed=completed,
            total=total,
            active=active,
            progress_percentage=f"{progress_percentage:.1f}%",
        )

    def get_orchestration_metrics(self) -> dict[str, Any]:
        """Get orchestration metrics for monitoring.

        Returns:
            Dictionary containing orchestration metrics

        """
        return {
            "active_agents": len(self._active_agents),
            "max_concurrent_agents": self.max_concurrent_agents,
            "completed_tasks": len([r for r in self._task_results.values() if r.success]),
            "failed_tasks": len([r for r in self._task_results.values() if not r.success]),
            "total_tasks_processed": len(self._task_results),
            "agent_utilization": len(self._active_agents) / self.max_concurrent_agents * 100,
        }

    async def cleanup(self) -> None:
        """Clean up orchestrator resources."""
        # Terminate any remaining active agents
        for agent_id in list(self._active_agents.keys()):
            try:
                await self.coordinator.terminate_agent(agent_id)
            except Exception as e:
                logger.warning(f"Failed to terminate agent {agent_id}: {e}")

        self._active_agents.clear()
        self._task_results.clear()

        logger.info("Agent orchestrator cleaned up")
