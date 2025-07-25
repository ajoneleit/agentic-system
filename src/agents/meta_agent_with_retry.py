"""Extended Meta Agent with retry logic and failure reporting.

This module extends MetaAgentWithVerification to add:
- Automatic retry for failed tasks
- Detailed failure reports
- Better error handling for Claude CLI issues
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from src.agents.meta_agent_with_verification import MetaAgentWithVerification
from src.core.exceptions import TaskError
from src.core.interfaces import Agent, Task, TaskContext
from src.utils.app_logging import get_logger
from src.verification.verifier_base import VerificationConfig

logger = get_logger(__name__)


class TaskFailureReport:
    """Detailed report of a task failure."""

    def __init__(self, task: Task, error: str, attempt: int, timestamp: datetime):
        self.task_id = task.id
        self.task_name = task.name
        self.error = error
        self.attempt = attempt
        self.timestamp = timestamp
        self.agent_id = None
        self.cli_response = None
        self.suggestions = []

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_id": str(self.task_id),
            "task_name": self.task_name,
            "error": self.error,
            "attempt": self.attempt,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": str(self.agent_id) if self.agent_id else None,
            "cli_response": self.cli_response,
            "suggestions": self.suggestions,
        }


class MetaAgentWithRetry(MetaAgentWithVerification):
    """Meta Agent with retry logic and detailed failure reporting."""

    def __init__(
        self,
        artifact_storage_path: Optional[Path] = None,
        verification_config: Optional[VerificationConfig] = None,
        max_retries: int = 3,
        retry_delay: float = 5.0,
    ):
        """Initialize Meta Agent with retry capabilities.

        Args:
            artifact_storage_path: Path for artifact storage
            verification_config: Configuration for verification
            max_retries: Maximum retry attempts per task
            retry_delay: Delay between retries in seconds

        """
        super().__init__(artifact_storage_path, verification_config)

        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.failure_reports: list[TaskFailureReport] = []
        self.task_retry_counts: dict[UUID, int] = {}

        # Track CLI responses for debugging
        self.cli_responses: dict[UUID, list[str]] = {}

    async def _execute_tasks(self, tasks: list[Task], context: TaskContext) -> None:
        """Execute tasks with retry logic and better error handling.

        Args:
            tasks: Tasks to execute
            context: Execution context

        """
        # Initialize verification if needed
        if self.enable_verification:
            await self._initialize_verification()

        completed_tasks: set[UUID] = set()
        failed_tasks: set[UUID] = set()
        active_agents: dict[UUID, Agent] = {}

        while len(completed_tasks) + len(failed_tasks) < len(tasks):
            # Get next batch of ready tasks
            ready_tasks = await self.task_manager.get_next_tasks()

            # Check for deadlock
            if not ready_tasks and not active_agents:
                blocked_tasks = await self.task_manager.get_blocked_tasks()

                # Try to resolve deadlock by retrying failed prerequisite tasks
                if blocked_tasks and failed_tasks:
                    resolved = await self._try_resolve_deadlock(
                        blocked_tasks, failed_tasks, tasks, context
                    )
                    if resolved:
                        continue

                if blocked_tasks:
                    # Generate failure report for deadlock
                    await self._generate_deadlock_report(blocked_tasks, failed_tasks)

                    logger.error(
                        "Deadlock detected - generating failure report",
                        blocked_count=len(blocked_tasks),
                        failed_count=len(failed_tasks),
                    )
                    raise TaskError("Task execution deadlocked - see failure report")

                logger.debug("No ready tasks, waiting for active agents")
                await asyncio.sleep(0.1)
                continue

            # Process ready tasks
            for task in ready_tasks:
                if task.id in active_agents:
                    continue

                try:
                    # Spawn agent
                    agent = await self.spawn_agent(task.agent_role, context)
                    active_agents[task.id] = agent

                    # Assign and execute task with retry
                    success = await self._execute_task_with_retry(task, agent, context)

                    if success:
                        # Verify if enabled
                        if self.enable_verification:
                            verification_passed = await self._verify_task(task)
                            if not verification_passed and self.enable_auto_repair:
                                await self._attempt_repair(task, context)

                        completed_tasks.add(task.id)
                    else:
                        failed_tasks.add(task.id)
                        # Create failure report
                        await self._create_task_failure_report(task)

                except Exception as e:
                    logger.error("Failed to execute task", task_id=task.id, error=str(e))
                    failed_tasks.add(task.id)
                    await self.task_manager.mark_task_failed(task.id, str(e))
                finally:
                    # Clean up agent
                    if task.id in active_agents:
                        del active_agents[task.id]

        # Generate final report
        await self._generate_final_report(tasks, completed_tasks, failed_tasks)

    async def _execute_task_with_retry(
        self, task: Task, agent: Agent, context: TaskContext
    ) -> bool:
        """Execute a task with retry logic.

        Args:
            task: Task to execute
            agent: Agent to execute the task
            context: Execution context

        Returns:
            True if task succeeded, False otherwise

        """
        task_id = task.id
        self.task_retry_counts[task_id] = 0

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
                await self.assign_task(task, agent)
                await agent.execute_task(task, context)

                # Check for CLI response issues
                if hasattr(agent, "_last_cli_response"):
                    cli_response = agent._last_cli_response
                    if task_id not in self.cli_responses:
                        self.cli_responses[task_id] = []
                    self.cli_responses[task_id].append(cli_response)

                    # Check for known CLI errors
                    if len(cli_response) == 15:
                        logger.warning(
                            "Detected short CLI response - likely an error",
                            task_id=task_id,
                            response=cli_response,
                        )
                        raise TaskError(f"Claude CLI error: {cli_response}")

                # Success
                logger.info("Task executed successfully", task_id=task_id, attempt=attempt + 1)
                return True

            except Exception as e:
                self.task_retry_counts[task_id] = attempt + 1

                logger.warning(
                    "Task execution failed", task_id=task_id, attempt=attempt + 1, error=str(e)
                )

                # Create failure report for this attempt
                report = TaskFailureReport(
                    task=task, error=str(e), attempt=attempt + 1, timestamp=datetime.utcnow()
                )
                report.agent_id = agent.id

                # Add CLI response if available
                if task_id in self.cli_responses:
                    report.cli_response = self.cli_responses[task_id][-1]

                # Add suggestions based on error
                if "Failed to parse Claude response as JSON" in str(e):
                    report.suggestions.extend(
                        [
                            "Claude CLI returned non-JSON response",
                            "Consider using API directly instead of CLI",
                            "Check CLI prompt length - may be truncated",
                        ]
                    )
                elif "15" in str(e) or (report.cli_response and len(report.cli_response) == 15):
                    report.suggestions.extend(
                        [
                            "Claude CLI returned error message",
                            "Prompt may be too long or malformed",
                            "Try simplifying the task description",
                        ]
                    )

                self.failure_reports.append(report)

                # If not the last attempt, wait before retry
                if attempt < self.max_retries - 1:
                    logger.info(f"Retrying task in {self.retry_delay} seconds", task_id=task_id)
                    await asyncio.sleep(self.retry_delay)
                else:
                    # Final failure
                    await self.task_manager.mark_task_failed(
                        task_id, f"Failed after {self.max_retries} attempts: {str(e)}"
                    )

        return False

    async def _try_resolve_deadlock(
        self,
        blocked_tasks: list[Task],
        failed_tasks: set[UUID],
        all_tasks: list[Task],
        context: TaskContext,
    ) -> bool:
        """Try to resolve deadlock by retrying failed prerequisite tasks.

        Args:
            blocked_tasks: Tasks that are blocked
            failed_tasks: Set of failed task IDs
            all_tasks: All tasks in the project
            context: Execution context

        Returns:
            True if deadlock might be resolved, False otherwise

        """
        # Find failed tasks that are blocking others
        task_map = {task.id: task for task in all_tasks}
        blocking_failed_tasks = set()

        for blocked_task in blocked_tasks:
            for dep_id in blocked_task.dependencies:
                if dep_id in failed_tasks:
                    blocking_failed_tasks.add(dep_id)

        if not blocking_failed_tasks:
            return False

        logger.info(
            "Attempting to resolve deadlock by retrying failed prerequisites",
            failed_prerequisites=len(blocking_failed_tasks),
        )

        # Retry the failed prerequisite tasks
        for task_id in blocking_failed_tasks:
            task = task_map.get(task_id)
            if task:
                # Reset task status for retry
                await self.task_manager.reset_task(task_id)
                failed_tasks.remove(task_id)

        return True

    async def _create_task_failure_report(self, task: Task) -> None:
        """Create a detailed failure report for a task.

        Args:
            task: The failed task

        """
        # Report is created in _execute_task_with_retry
        pass

    async def _generate_deadlock_report(
        self, blocked_tasks: list[Task], failed_tasks: set[UUID]
    ) -> None:
        """Generate a report for deadlock situation.

        Args:
            blocked_tasks: Tasks that are blocked
            failed_tasks: Set of failed task IDs

        """
        report = {
            "type": "deadlock",
            "timestamp": datetime.utcnow().isoformat(),
            "blocked_tasks": [
                {
                    "id": str(task.id),
                    "name": task.name,
                    "dependencies": [str(d) for d in task.dependencies],
                }
                for task in blocked_tasks
            ],
            "failed_tasks": [str(tid) for tid in failed_tasks],
            "suggestions": [
                "Some tasks depend on failed tasks",
                "Consider simplifying task dependencies",
                "Review failed task reports for root causes",
            ],
        }

        # Save deadlock report
        report_path = self.project_path / "failure_reports" / "deadlock_report.json"
        report_path.parent.mkdir(exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Deadlock report saved to {report_path}")

    async def _generate_final_report(
        self, all_tasks: list[Task], completed_tasks: set[UUID], failed_tasks: set[UUID]
    ) -> None:
        """Generate final execution report.

        Args:
            all_tasks: All tasks that were executed
            completed_tasks: Set of completed task IDs
            failed_tasks: Set of failed task IDs

        """
        report = {
            "project_id": self._current_project_id,
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "total_tasks": len(all_tasks),
                "completed": len(completed_tasks),
                "failed": len(failed_tasks),
                "success_rate": len(completed_tasks) / len(all_tasks) if all_tasks else 0,
            },
            "completed_tasks": [
                {"id": str(task.id), "name": task.name}
                for task in all_tasks
                if task.id in completed_tasks
            ],
            "failed_tasks": [
                {
                    "id": str(task.id),
                    "name": task.name,
                    "retry_count": self.task_retry_counts.get(task.id, 0),
                }
                for task in all_tasks
                if task.id in failed_tasks
            ],
            "failure_details": [report.to_dict() for report in self.failure_reports],
            "recommendations": [],
        }

        # Add recommendations based on failures
        if self.failure_reports:
            cli_errors = sum(1 for r in self.failure_reports if "CLI" in r.error)
            if cli_errors > len(self.failure_reports) * 0.5:
                report["recommendations"].append(
                    "High rate of Claude CLI errors - consider using API directly"
                )

            json_errors = sum(1 for r in self.failure_reports if "JSON" in r.error)
            if json_errors > 0:
                report["recommendations"].append("Claude CLI responses not in expected JSON format")

        # Save report
        report_path = self.project_path / "failure_reports" / "execution_report.json"
        report_path.parent.mkdir(exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(
            f"Execution report saved to {report_path}",
            completed=len(completed_tasks),
            failed=len(failed_tasks),
        )

        # Also save a human-readable summary
        summary_path = self.project_path / "failure_reports" / "summary.md"
        with open(summary_path, "w") as f:
            f.write("# Execution Summary\n\n")
            f.write(f"Generated at: {datetime.utcnow().isoformat()}\n\n")
            f.write("## Results\n\n")
            f.write(f"- Total tasks: {len(all_tasks)}\n")
            f.write(f"- Completed: {len(completed_tasks)}\n")
            f.write(f"- Failed: {len(failed_tasks)}\n")
            f.write(f"- Success rate: {report['summary']['success_rate']:.1%}\n\n")

            if failed_tasks:
                f.write("## Failed Tasks\n\n")
                for task in all_tasks:
                    if task.id in failed_tasks:
                        f.write(f"### {task.name}\n")
                        f.write(f"- Task ID: {task.id}\n")
                        f.write(f"- Retry attempts: {self.task_retry_counts.get(task.id, 0)}\n")

                        # Find related failure reports
                        task_reports = [r for r in self.failure_reports if r.task_id == task.id]
                        if task_reports:
                            f.write("- Errors:\n")
                            for report in task_reports:
                                f.write(f"  - Attempt {report.attempt}: {report.error}\n")
                                if report.cli_response:
                                    f.write(f"    - CLI response: `{report.cli_response}`\n")
                        f.write("\n")

            if report["recommendations"]:
                f.write("## Recommendations\n\n")
                for rec in report["recommendations"]:
                    f.write(f"- {rec}\n")


# Import asyncio for sleep
import asyncio
