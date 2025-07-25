"""Error Handler for MetaAgent modularization.

This module handles error handling, retry logic, and failure analysis
for the MetaAgent system. It provides comprehensive error diagnosis
and adaptive retry strategies.
"""

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

from structlog import get_logger

from src.core.failure_analyzer import FailureAnalyzer
from src.core.interfaces import Agent, Task, TaskContext
from src.core.task_manager import TaskManager
from src.core.task_result import TaskResult

logger = get_logger(__name__)


class ErrorHandler:
    """Manages error handling and retry logic for MetaAgent."""

    def __init__(
        self,
        failure_analyzer: FailureAnalyzer,
        task_manager: TaskManager,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        retry_backoff: float = 2.0,
        diagnose_failures: bool = True,
        retry_on_verification_failure: bool = True,
        retry_on_api_errors: bool = True,
    ):
        """Initialize error handler.

        Args:
            failure_analyzer: Failure analyzer instance
            task_manager: Task manager instance
            max_retries: Maximum number of retry attempts
            retry_delay: Base delay between retries in seconds
            retry_backoff: Exponential backoff multiplier
            diagnose_failures: Whether to perform failure diagnosis
            retry_on_verification_failure: Whether to retry on verification failures
            retry_on_api_errors: Whether to retry on API errors

        """
        self.failure_analyzer = failure_analyzer
        self.task_manager = task_manager
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.retry_backoff = retry_backoff
        self.diagnose_failures = diagnose_failures
        self.retry_on_verification_failure = retry_on_verification_failure
        self.retry_on_api_errors = retry_on_api_errors

        # Task retry tracking
        self._task_retry_counts: dict[UUID, int] = {}
        self._task_retry_history: dict[UUID, list[dict[str, Any]]] = {}

        logger.info(
            "Error handler initialized",
            max_retries=max_retries,
            retry_delay=retry_delay,
            retry_backoff=retry_backoff,
            diagnose_failures=diagnose_failures,
        )

    async def execute_task_with_retry(
        self, task: Task, agent: Agent, context: TaskContext
    ) -> TaskResult:
        """Execute a task with comprehensive retry logic.

        Args:
            task: Task to execute
            agent: Agent to execute the task
            context: Execution context

        Returns:
            Task result after all retry attempts

        """
        task_id = task.id
        if task_id not in self._task_retry_counts:
            self._task_retry_counts[task_id] = 0
            self._task_retry_history[task_id] = []

        last_error = None
        for attempt in range(self.max_retries):
            try:
                logger.info(
                    "Executing task",
                    task_id=task_id,
                    task_name=task.name,
                    attempt=attempt + 1,
                    max_attempts=self.max_retries,
                )

                # Execute task
                await self.task_manager.start_task(task_id)
                task_result = await agent.execute_task(task, context)

                # Check for success
                if task_result.success:
                    logger.info("Task executed successfully", task_id=task_id, attempt=attempt + 1)
                    return task_result

                # Task failed but returned a result
                last_error = Exception(
                    "; ".join(task_result.errors) if task_result.errors else "Task failed"
                )

                # Analyze failure if diagnosis is enabled
                if self.diagnose_failures:
                    await self._handle_task_failure(task, last_error, agent, attempt + 1, context)

            except Exception as e:
                last_error = e
                logger.warning(
                    "Task execution failed", task_id=task_id, attempt=attempt + 1, error=str(e)
                )

                # Analyze failure
                if self.diagnose_failures:
                    await self._handle_task_failure(task, e, agent, attempt + 1, context)

            # Check if we should retry
            self._task_retry_counts[task_id] = attempt + 1

            if attempt < self.max_retries - 1:
                # Determine retry delay
                retry_delay = await self._calculate_retry_delay(task, last_error, attempt + 1)

                logger.info(
                    f"Retrying task in {retry_delay} seconds", task_id=task_id, attempt=attempt + 1
                )
                await asyncio.sleep(retry_delay)

                # Modify task for retry if needed
                await self._prepare_task_for_retry(task, last_error, attempt + 1)

        # All retries exhausted
        error_result = TaskResult(
            task_id=task_id,
            agent_id=agent.id,
            success=False,
        )
        error_msg = f"Failed after {self.max_retries} attempts: {str(last_error)}"
        error_result.add_error(error_msg)

        logger.error(
            "Task failed after all retries",
            task_id=task_id,
            task_name=task.name,
            total_attempts=self.max_retries,
            final_error=error_msg,
        )

        return error_result

    async def _handle_task_failure(
        self, task: Task, error: Exception, agent: Agent, attempt: int, context: TaskContext
    ) -> None:
        """Handle a task failure by analyzing and logging it.

        Args:
            task: Failed task
            error: The error that occurred
            agent: Agent that executed the task
            attempt: Attempt number
            context: Execution context

        """
        # Get CLI response if available
        cli_response = None
        if hasattr(agent, "_last_cli_response"):
            cli_response = agent._last_cli_response

        # Analyze error
        diagnosis_context = {
            "attempt": attempt,
            "max_attempts": self.max_retries,
            "agent_id": agent.id,
            "cli_response": cli_response,
            "error_message": str(error),
            "base_delay": self.retry_delay,
            "backoff_multiplier": self.retry_backoff,
        }

        diagnosis = await self.failure_analyzer.analyze_error(task, error, diagnosis_context)

        # Record retry history
        self._task_retry_history[task.id].append(
            {
                "attempt": attempt,
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(error),
                "diagnosis": diagnosis,
                "cli_response": cli_response,
            }
        )

        # Log structured failure information
        logger.error(
            "task_retry_failure",
            task_id=task.id,
            task_name=task.name,
            attempt=attempt,
            error_type=diagnosis.error_type.value,
            is_retryable=diagnosis.is_retryable,
            retry_strategy=diagnosis.retry_strategy.value,
            suggested_fix=diagnosis.suggested_fix,
        )

    async def _calculate_retry_delay(self, task: Task, error: Exception, attempt: int) -> float:
        """Calculate delay before retry.

        Args:
            task: Failed task
            error: The error that occurred
            attempt: Attempt number

        Returns:
            Delay in seconds before next retry

        """
        # Base exponential backoff
        base_delay = self.retry_delay * (self.retry_backoff ** (attempt - 1))

        # Analyze error for specific delay adjustments
        error_str = str(error).lower()

        # API rate limiting
        if "rate limit" in error_str or "too many requests" in error_str:
            return max(base_delay, 60.0)  # At least 1 minute for rate limits

        # Network/connection errors
        if any(term in error_str for term in ["connection", "network", "timeout"]):
            return max(base_delay, 10.0)  # At least 10 seconds for network issues

        # Verification failures (shorter delay)
        if "verification" in error_str or "compilation" in error_str:
            return min(base_delay, 5.0)  # Max 5 seconds for quick fixes

        return base_delay

    async def _prepare_task_for_retry(self, task: Task, error: Exception, attempt: int) -> None:
        """Prepare task for retry based on the error.

        Args:
            task: Task to prepare for retry
            error: The error that occurred
            attempt: Attempt number

        """
        # Analyze error to determine if task modification is needed
        error_str = str(error).lower()

        # Add retry context to task description
        if not hasattr(task, "_retry_context"):
            task._retry_context = []

        task._retry_context.append(
            {"attempt": attempt, "error": str(error), "timestamp": datetime.utcnow().isoformat()}
        )

        # Modify task description to include retry guidance
        if attempt == 2:  # Second retry, add more context
            task.description += f"\n\nIMPORTANT: This is retry attempt {attempt}. "

            if "file not found" in error_str:
                task.description += "Previous attempts failed because required files were missing. Ensure you create all necessary files first."
            elif "compilation" in error_str or "syntax" in error_str:
                task.description += "Previous attempts had compilation/syntax errors. Double-check your code syntax carefully."
            elif "verification" in error_str:
                task.description += "Previous attempts failed verification. Focus on meeting all requirements exactly."
            elif "dependency" in error_str:
                task.description += "Previous attempts had dependency issues. Verify all imports and dependencies are correct."

        logger.debug(
            "Task prepared for retry",
            task_id=task.id,
            attempt=attempt,
            retry_context_count=len(task._retry_context),
        )

    async def try_resolve_deadlock(
        self,
        blocked_tasks: list[Task],
        failed_tasks: set[UUID],
        all_tasks: list[Task],
        context: TaskContext,
    ) -> bool:
        """Try to resolve execution deadlock by retrying failed prerequisites.

        Args:
            blocked_tasks: Tasks that are blocked
            failed_tasks: Set of failed task IDs
            all_tasks: All tasks in the execution
            context: Execution context

        Returns:
            True if deadlock was resolved, False otherwise

        """
        if not blocked_tasks:
            return False

        # Find failed tasks that are prerequisites for blocked tasks
        retryable_failed = []
        for blocked_task in blocked_tasks:
            for dep_id in blocked_task.dependencies:
                if dep_id in failed_tasks:
                    # Find the failed task
                    failed_task = next((t for t in all_tasks if t.id == dep_id), None)
                    if failed_task and self._is_task_retryable(failed_task):
                        retryable_failed.append(failed_task)

        if not retryable_failed:
            logger.warning("No retryable failed tasks found to resolve deadlock")
            return False

        logger.info(
            "Attempting to resolve deadlock by retrying failed prerequisites",
            retryable_count=len(retryable_failed),
            retryable_tasks=[t.name for t in retryable_failed],
        )

        # Reset failed tasks to pending for retry
        for task in retryable_failed:
            failed_tasks.discard(task.id)
            await self.task_manager.reset_task(task.id)

            # Clear retry count to allow fresh attempts
            if task.id in self._task_retry_counts:
                self._task_retry_counts[task.id] = 0

        return True

    def _is_task_retryable(self, task: Task) -> bool:
        """Check if a task is eligible for retry.

        Args:
            task: Task to check

        Returns:
            True if task can be retried, False otherwise

        """
        retry_count = self._task_retry_counts.get(task.id, 0)

        # Don't retry if already at max attempts
        if retry_count >= self.max_retries:
            return False

        # Check retry history for patterns
        history = self._task_retry_history.get(task.id, [])
        if not history:
            return True

        # Don't retry if last error was non-retryable
        last_attempt = history[-1]
        if "diagnosis" in last_attempt:
            diagnosis = last_attempt["diagnosis"]
            if hasattr(diagnosis, "is_retryable") and not diagnosis.is_retryable:
                return False

        return True

    def get_retry_statistics(self) -> dict[str, Any]:
        """Get retry statistics for monitoring.

        Returns:
            Dictionary containing retry statistics

        """
        total_tasks = len(self._task_retry_counts)
        total_retries = sum(self._task_retry_counts.values())

        # Categorize tasks by retry count
        retry_distribution = {}
        for count in self._task_retry_counts.values():
            retry_distribution[count] = retry_distribution.get(count, 0) + 1

        # Find most problematic tasks
        problematic_tasks = [
            {"task_id": str(task_id), "retry_count": count}
            for task_id, count in self._task_retry_counts.items()
            if count >= self.max_retries // 2
        ]

        return {
            "total_tasks_with_retries": total_tasks,
            "total_retry_attempts": total_retries,
            "average_retries_per_task": total_retries / total_tasks if total_tasks > 0 else 0,
            "retry_distribution": retry_distribution,
            "problematic_tasks": problematic_tasks,
            "max_retries_configured": self.max_retries,
            "base_retry_delay": self.retry_delay,
            "retry_backoff_factor": self.retry_backoff,
        }

    def get_task_retry_history(self, task_id: UUID) -> list[dict[str, Any]]:
        """Get retry history for a specific task.

        Args:
            task_id: ID of the task

        Returns:
            List of retry attempt records

        """
        return self._task_retry_history.get(task_id, [])

    def reset_task_retry_tracking(self, task_id: UUID) -> None:
        """Reset retry tracking for a specific task.

        Args:
            task_id: ID of the task to reset

        """
        self._task_retry_counts.pop(task_id, None)
        self._task_retry_history.pop(task_id, None)

        logger.debug("Reset retry tracking for task", task_id=str(task_id))

    def create_error_task_result(
        self, task_id: UUID, agent_id: UUID, error_message: str
    ) -> TaskResult:
        """Create a TaskResult for an error scenario.

        Args:
            task_id: ID of the failed task
            agent_id: ID of the agent that failed
            error_message: Error message to include

        Returns:
            TaskResult representing the error

        """
        error_result = TaskResult(
            task_id=task_id,
            agent_id=agent_id,
            success=False,
        )
        error_result.add_error(error_message)

        return error_result
