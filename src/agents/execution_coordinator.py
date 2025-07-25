"""Task execution coordination module.

This module provides the ExecutionCoordinator class that manages task execution,
agent coordination, and failure recovery.
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

from structlog import get_logger

from src.agents.sub_agent import (
    CodeGeneratorAgent,
    DebugAgent,
    DocumentationAgent,
    RefactorAgent,
    TestWriterAgent,
)
from src.core.exceptions import AgentError, TaskExecutionError
from src.core.interfaces import Agent, AgentRole, Task, TaskContext, TaskStatus
from src.core.result import Result
from src.core.task_result import TaskResult
from src.utils.app_logging import log_execution_time

logger = get_logger(__name__)


class ExecutionCoordinator:
    """Coordinates task execution and agent management."""

    def __init__(self, max_parallel_tasks: int = 3, task_timeout: int = 300):
        """Initialize the execution coordinator.

        Args:
            max_parallel_tasks: Maximum number of parallel tasks
            task_timeout: Timeout for task execution in seconds

        """
        self.max_parallel_tasks = max_parallel_tasks
        self.task_timeout = task_timeout
        self._active_agents: dict[UUID, Agent] = {}
        self._task_semaphore = asyncio.Semaphore(max_parallel_tasks)
        self._execution_stats = {
            "total_tasks": 0,
            "successful_tasks": 0,
            "failed_tasks": 0,
            "total_execution_time": 0.0,
        }

    @log_execution_time("coordinate_execution")
    async def coordinate_execution(
        self, tasks: list[Task], context: TaskContext
    ) -> Result[dict[str, TaskResult]]:
        """Coordinate execution of tasks with dependency resolution.

        Args:
            tasks: List of tasks to execute
            context: Task execution context

        Returns:
            Result containing dictionary of task results or error

        """
        try:
            logger.info(
                "Starting task execution coordination",
                task_count=len(tasks),
                max_parallel=self.max_parallel_tasks,
            )

            # Initialize execution tracking
            results: dict[str, TaskResult] = {}
            completed_tasks: set[UUID] = set()
            failed_tasks: set[UUID] = set()

            # Execute tasks in dependency order
            while len(completed_tasks) + len(failed_tasks) < len(tasks):
                # Get ready tasks (dependencies satisfied)
                ready_tasks = self._get_ready_tasks(tasks, completed_tasks, failed_tasks)

                if not ready_tasks:
                    # Check for deadlock
                    remaining_tasks = [
                        t for t in tasks if t.id not in completed_tasks and t.id not in failed_tasks
                    ]
                    if remaining_tasks:
                        logger.error(
                            "Deadlock detected", remaining_tasks=[t.name for t in remaining_tasks]
                        )
                        return Result.failure(TaskExecutionError("Deadlock in task execution"))
                    break

                # Execute ready tasks in parallel
                execution_results = await self._execute_tasks_parallel(ready_tasks, context)

                # Process results
                for task_id, result in execution_results.items():
                    results[str(task_id)] = result
                    if result.success:
                        completed_tasks.add(task_id)
                        self._execution_stats["successful_tasks"] += 1
                    else:
                        failed_tasks.add(task_id)
                        self._execution_stats["failed_tasks"] += 1

                        # Log failure
                        logger.error(
                            "Task execution failed",
                            task_id=str(task_id),
                            error=result.errors[0] if result.errors else "Unknown error",
                        )

                self._execution_stats["total_tasks"] += len(execution_results)

            # Calculate success rate
            total_tasks = len(tasks)
            successful_tasks = len(completed_tasks)
            success_rate = (successful_tasks / total_tasks) * 100 if total_tasks > 0 else 0

            logger.info(
                "Task execution coordination completed",
                total_tasks=total_tasks,
                successful_tasks=successful_tasks,
                failed_tasks=len(failed_tasks),
                success_rate=success_rate,
            )

            return Result.success(results)

        except Exception as e:
            logger.error("Task execution coordination failed", error=str(e), exc_info=True)
            return Result.failure(
                TaskExecutionError(
                    task_id=uuid4(),  # Use a dummy task ID since this is coordinator level
                    agent_id=uuid4(),  # Use a dummy agent ID
                    reason=f"Execution coordination failed: {str(e)}",
                )
            )

    async def _execute_tasks_parallel(
        self, tasks: list[Task], context: TaskContext
    ) -> dict[UUID, TaskResult]:
        """Execute tasks in parallel with concurrency control.

        Args:
            tasks: List of tasks to execute
            context: Task execution context

        Returns:
            Dictionary of task results

        """
        # Create execution coroutines
        execution_coros = []
        for task in tasks:
            coro = self._execute_single_task(task, context)
            execution_coros.append(coro)

        # Execute with timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*execution_coros, return_exceptions=True),
                timeout=self.task_timeout * len(tasks),
            )

            # Process results
            task_results = {}
            for i, result in enumerate(results):
                task_id = tasks[i].id
                if isinstance(result, Exception):
                    task_results[task_id] = TaskResult(
                        task_id=task_id,
                        agent_id=tasks[i].assigned_agent_id or uuid4(),
                        success=False,
                        errors=[str(result)],
                        execution_time=0.0,
                    )
                else:
                    task_results[task_id] = result

            return task_results

        except asyncio.TimeoutError:
            logger.error("Parallel task execution timed out")
            # Return failure results for all tasks
            return {
                task.id: TaskResult(
                    task_id=task.id,
                    agent_id=task.assigned_agent_id or uuid4(),
                    success=False,
                    errors=["Task execution timed out"],
                    execution_time=0.0,
                )
                for task in tasks
            }

    async def _execute_single_task(self, task: Task, context: TaskContext) -> TaskResult:
        """Execute a single task with retry logic.

        Args:
            task: Task to execute
            context: Task execution context

        Returns:
            Task execution result

        """
        async with self._task_semaphore:
            try:
                start_time = datetime.now(timezone.utc)

                # Update task status
                task.status = TaskStatus.IN_PROGRESS
                task.started_at = start_time

                # Get or create agent for task
                agent = await self._get_agent_for_task(task, context)

                # Execute task with timeout
                result = await asyncio.wait_for(
                    agent.execute_task(task, context), timeout=self.task_timeout
                )

                # Calculate execution time
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

                # Update task status
                if result.success:
                    task.status = TaskStatus.COMPLETED
                    task.completed_at = datetime.now(timezone.utc)
                else:
                    task.status = TaskStatus.FAILED

                # Update result with execution time
                result.execution_time = execution_time
                self._execution_stats["total_execution_time"] += execution_time

                logger.info(
                    "Task executed",
                    task_id=str(task.id),
                    task_name=task.name,
                    success=result.success,
                    execution_time=execution_time,
                )

                return result

            except asyncio.TimeoutError:
                logger.error("Task execution timed out", task_id=str(task.id))
                task.status = TaskStatus.FAILED
                return TaskResult(
                    task_id=task.id,
                    agent_id=task.assigned_agent_id or uuid4(),
                    success=False,
                    errors=[f"Task execution timed out after {self.task_timeout} seconds"],
                    execution_time=self.task_timeout,
                )

            except Exception as e:
                logger.error("Task execution failed", task_id=str(task.id), error=str(e))
                task.status = TaskStatus.FAILED
                return TaskResult(
                    task_id=task.id,
                    agent_id=task.assigned_agent_id or uuid4(),
                    success=False,
                    errors=[str(e)],
                    execution_time=0.0,
                )

    async def _get_agent_for_task(self, task: Task, context: TaskContext) -> Agent:
        """Get or create appropriate agent for task.

        Args:
            task: Task to get agent for
            context: Task execution context

        Returns:
            Agent instance

        """
        # Map task types to agent roles
        task_type_to_role = {
            "code_generation": AgentRole.CORE_LOGIC,
            "testing": AgentRole.TESTING,
            "documentation": AgentRole.DOCUMENTATION,
            "optimization": AgentRole.OPTIMIZATION,
            "verification": AgentRole.VERIFICATION,
            "general": AgentRole.CORE_LOGIC,
        }

        # Use the task's required_role if available, otherwise default to CORE_LOGIC
        if task.required_role:
            role = task.required_role
        else:
            # Use metadata type if available
            task_type = task.metadata.get("type", "general")
            role = task_type_to_role.get(task_type, AgentRole.CORE_LOGIC)

        # Check if we have an active agent for this role
        for _agent_id, agent in self._active_agents.items():
            if agent.role == role:
                return agent

        # Create new agent using factory function
        agent = self._create_agent_for_role(task.id, role)

        # Initialize agent
        init_result = await agent.initialize(context)
        if init_result.is_failure():
            raise AgentError(agent.id, f"Failed to initialize agent: {init_result.get_error()}")

        # Store agent reference
        self._active_agents[agent.id] = agent

        logger.info(
            "Agent created for task", task_id=str(task.id), agent_id=str(agent.id), role=role.value
        )

        return agent

    def _create_agent_for_role(self, agent_id: UUID, role: AgentRole) -> Agent:
        """Create appropriate concrete agent for the given role.

        Args:
            agent_id: Unique agent identifier
            role: Agent role to create

        Returns:
            Concrete agent instance

        """
        if role == AgentRole.CORE_LOGIC:
            return CodeGeneratorAgent(agent_id)
        elif role == AgentRole.TESTING:
            return TestWriterAgent(agent_id)
        elif role == AgentRole.DOCUMENTATION:
            return DocumentationAgent(agent_id)
        elif role == AgentRole.OPTIMIZATION:
            return RefactorAgent(agent_id)
        elif role == AgentRole.VERIFICATION:
            return DebugAgent(agent_id)
        else:
            # Default to CodeGeneratorAgent for unknown roles
            return CodeGeneratorAgent(agent_id)

    def _get_ready_tasks(
        self, tasks: list[Task], completed: set[UUID], failed: set[UUID]
    ) -> list[Task]:
        """Get tasks that are ready to execute (dependencies satisfied).

        Args:
            tasks: All tasks
            completed: Set of completed task IDs
            failed: Set of failed task IDs

        Returns:
            List of ready tasks

        """
        ready_tasks = []

        for task in tasks:
            # Skip if already processed
            if task.id in completed or task.id in failed:
                continue

            # Check if dependencies are satisfied
            dependencies_satisfied = True
            for dep_id in task.dependencies:
                if dep_id not in completed:
                    dependencies_satisfied = False
                    break

            if dependencies_satisfied:
                ready_tasks.append(task)

        return ready_tasks

    async def handle_task_failure(self, task: Task, error: Exception) -> Result[None]:
        """Handle task failure with recovery attempts.

        Args:
            task: Failed task
            error: Error that caused failure

        Returns:
            Result indicating if recovery was attempted

        """
        try:
            logger.warning(
                "Handling task failure", task_id=str(task.id), task_name=task.name, error=str(error)
            )

            # Analyze failure type
            failure_type = self._analyze_failure_type(error)

            # Determine recovery strategy
            recovery_strategy = self._get_recovery_strategy(failure_type)

            # Log recovery attempt
            logger.info(
                "Attempting task recovery",
                task_id=str(task.id),
                failure_type=failure_type,
                recovery_strategy=recovery_strategy,
            )

            # For now, just log the failure - actual recovery would be implemented here
            return Result.success(None)

        except Exception as e:
            logger.error("Task failure handling failed", error=str(e))
            return Result.failure(TaskExecutionError(f"Failed to handle task failure: {str(e)}"))

    def _analyze_failure_type(self, error: Exception) -> str:
        """Analyze the type of failure.

        Args:
            error: The error that occurred

        Returns:
            Failure type classification

        """
        error_str = str(error).lower()

        if "timeout" in error_str:
            return "timeout"
        elif "api" in error_str or "rate limit" in error_str:
            return "api_error"
        elif "network" in error_str or "connection" in error_str:
            return "network_error"
        elif "permission" in error_str or "access" in error_str:
            return "permission_error"
        elif "syntax" in error_str or "compile" in error_str:
            return "code_error"
        else:
            return "unknown"

    def _get_recovery_strategy(self, failure_type: str) -> str:
        """Get recovery strategy for failure type.

        Args:
            failure_type: Type of failure

        Returns:
            Recovery strategy

        """
        strategies = {
            "timeout": "increase_timeout",
            "api_error": "retry_with_backoff",
            "network_error": "retry_with_backoff",
            "permission_error": "check_permissions",
            "code_error": "request_fix",
            "unknown": "manual_review",
        }

        return strategies.get(failure_type, "manual_review")

    async def cleanup_agents(self) -> None:
        """Clean up active agents."""
        for agent_id, agent in self._active_agents.items():
            try:
                if hasattr(agent, "cleanup"):
                    await agent.cleanup()
            except Exception as e:
                logger.error("Agent cleanup failed", agent_id=str(agent_id), error=str(e))

        self._active_agents.clear()
        logger.info("All agents cleaned up")

    def get_execution_stats(self) -> dict[str, any]:
        """Get execution statistics.

        Returns:
            Dictionary of execution statistics

        """
        return self._execution_stats.copy()

    def reset_stats(self) -> None:
        """Reset execution statistics."""
        self._execution_stats = {
            "total_tasks": 0,
            "successful_tasks": 0,
            "failed_tasks": 0,
            "total_execution_time": 0.0,
        }
        logger.info("Execution statistics reset")
