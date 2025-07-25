"""Integration of verification system with Meta Agent."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from src.core.interfaces import (
    AgentRole,
    Artifact,
    Task,
    TaskPriority,
    TaskStatus,
)
from src.utils.app_logging import get_logger

from .pipeline import VerificationPipeline
from .repair_analyzer import RepairAnalyzer, RepairSuggestion
from .verifier_base import VerificationConfig, VerificationResult, VerificationType

logger = get_logger(__name__)


@dataclass
class TaskVerificationResult:
    """Verification results for a specific task."""

    task_id: UUID
    task_name: str
    success: bool

    # Artifact verification results
    artifact_results: dict[UUID, list[VerificationResult]]

    # Summary
    total_verifications: int = 0
    passed_verifications: int = 0
    failed_verifications: int = 0

    # Critical issues
    has_syntax_errors: bool = False
    has_compilation_errors: bool = False
    has_test_failures: bool = False

    # Suggestions
    repair_suggestions: list[RepairSuggestion] = None

    def __post_init__(self):
        """Calculate summary statistics."""
        self.repair_suggestions = self.repair_suggestions or []

        for _artifact_id, results in self.artifact_results.items():
            for result in results:
                self.total_verifications += 1
                if result.success:
                    self.passed_verifications += 1
                else:
                    self.failed_verifications += 1

                    # Check for critical issues
                    if result.verification_type == VerificationType.SYNTAX:
                        self.has_syntax_errors = True
                    elif result.verification_type == VerificationType.COMPILATION:
                        self.has_compilation_errors = True
                    elif result.verification_type == VerificationType.TEST:
                        self.has_test_failures = True


@dataclass
class ProjectVerificationResult:
    """Verification results for an entire project."""

    project_id: str
    success: bool

    # Task results
    task_results: dict[UUID, TaskVerificationResult]

    # Summary
    total_tasks: int = 0
    verified_tasks: int = 0
    failed_tasks: int = 0

    # Metrics
    overall_test_coverage: Optional[float] = None
    total_tests_run: int = 0
    total_tests_passed: int = 0

    # Timing
    started_at: datetime = None
    completed_at: datetime = None
    execution_time: float = 0.0

    def __post_init__(self):
        """Calculate project-level statistics."""
        self.total_tasks = len(self.task_results)

        for task_result in self.task_results.values():
            if task_result.success:
                self.verified_tasks += 1
            else:
                self.failed_tasks += 1

        # Calculate overall success
        self.success = self.failed_tasks == 0


class VerificationIntegration:
    """Integrates verification system with Meta Agent workflow."""

    def __init__(self, artifact_manager, task_manager, config: Optional[VerificationConfig] = None):
        """Initialize verification integration.

        Args:
            artifact_manager: Artifact manager instance
            task_manager: Task manager instance
            config: Verification configuration

        """
        self.artifact_manager = artifact_manager
        self.task_manager = task_manager
        self.config = config or VerificationConfig()
        self.pipeline = VerificationPipeline(config)
        self.repair_analyzer = RepairAnalyzer()

    async def verify_task_artifacts(self, task: Task) -> TaskVerificationResult:
        """Verify all artifacts produced by a task.

        Args:
            task: The task to verify

        Returns:
            Task verification result

        """
        logger.info(f"Verifying artifacts for task {task.id}: {task.name}")

        # Fetch task artifacts
        artifacts = await self._fetch_task_artifacts(task)

        if not artifacts:
            logger.info(f"No artifacts to verify for task {task.id}")
            return TaskVerificationResult(
                task_id=task.id,
                task_name=task.name,
                success=True,
                artifact_results={},
            )

        # Run verification pipeline
        pipeline_result = await self.pipeline.verify_artifacts(artifacts)

        # Create task verification result
        task_result = TaskVerificationResult(
            task_id=task.id,
            task_name=task.name,
            success=pipeline_result.success,
            artifact_results=pipeline_result.verification_results,
        )

        # Generate repair suggestions if needed
        if not task_result.success:
            repair_suggestions = await self._generate_repair_suggestions(
                task, artifacts, pipeline_result.verification_results
            )
            task_result.repair_suggestions = repair_suggestions

        # Update task status based on verification
        await self._update_task_status(task, task_result)

        return task_result

    async def verify_project(self, project_id: str) -> ProjectVerificationResult:
        """Verify all tasks in a project.

        Args:
            project_id: The project ID to verify

        Returns:
            Project verification result

        """
        logger.info(f"Verifying project {project_id}")

        result = ProjectVerificationResult(
            project_id=project_id,
            success=True,
            task_results={},
            started_at=datetime.utcnow(),
        )

        # Get all tasks for the project
        all_tasks = await self.task_manager.get_tasks_by_project(project_id)

        # Verify each task
        for task in all_tasks:
            if task.status == TaskStatus.COMPLETED:
                task_result = await self.verify_task_artifacts(task)
                result.task_results[task.id] = task_result

                # Update project-level metrics
                self._update_project_metrics(result, task_result)

        result.completed_at = datetime.utcnow()
        result.execution_time = (result.completed_at - result.started_at).total_seconds()

        logger.info(
            f"Project verification complete: {result.verified_tasks} passed, "
            f"{result.failed_tasks} failed"
        )

        return result

    async def generate_repair_tasks(
        self, verification_result: TaskVerificationResult
    ) -> list[Task]:
        """Generate repair tasks based on verification failures.

        Args:
            verification_result: The verification result with failures

        Returns:
            List of repair tasks

        """
        repair_tasks = []

        # Group failures by type
        syntax_errors = []
        compilation_errors = []
        test_failures = []

        for artifact_id, results in verification_result.artifact_results.items():
            for result in results:
                if not result.success:
                    if result.verification_type == VerificationType.SYNTAX:
                        syntax_errors.append((artifact_id, result))
                    elif result.verification_type == VerificationType.COMPILATION:
                        compilation_errors.append((artifact_id, result))
                    elif result.verification_type == VerificationType.TEST:
                        test_failures.append((artifact_id, result))

        # Create repair tasks for different failure types
        if syntax_errors:
            task = await self._create_syntax_repair_task(verification_result.task_id, syntax_errors)
            repair_tasks.append(task)

        if compilation_errors:
            task = await self._create_compilation_repair_task(
                verification_result.task_id, compilation_errors
            )
            repair_tasks.append(task)

        if test_failures:
            task = await self._create_test_repair_task(verification_result.task_id, test_failures)
            repair_tasks.append(task)

        return repair_tasks

    async def _fetch_task_artifacts(self, task: Task) -> list[Artifact]:
        """Fetch all artifacts for a task."""
        artifacts = []

        for artifact_id in task.artifacts:
            artifact = await self.artifact_manager.get_artifact(artifact_id)
            if artifact:
                artifacts.append(artifact)
            else:
                logger.warning(f"Could not fetch artifact {artifact_id} for task {task.id}")

        return artifacts

    async def _generate_repair_suggestions(
        self,
        task: Task,
        artifacts: list[Artifact],
        verification_results: dict[UUID, list[VerificationResult]],
    ) -> list[RepairSuggestion]:
        """Generate repair suggestions for verification failures."""
        suggestions = []

        for artifact in artifacts:
            if artifact.id in verification_results:
                for result in verification_results[artifact.id]:
                    if not result.success:
                        # Use repair analyzer to generate suggestions
                        suggestion = await self.repair_analyzer.analyze_failure(artifact, result)
                        if suggestion:
                            suggestions.append(suggestion)

        return suggestions

    async def _update_task_status(self, task: Task, result: TaskVerificationResult) -> None:
        """Update task status based on verification results."""
        if result.success:
            # Mark task as verified
            if hasattr(task, "metadata"):
                task.metadata["verified"] = True
                task.metadata["verification_time"] = datetime.utcnow().isoformat()
        else:
            # Mark task as needing repair
            if hasattr(task, "metadata"):
                task.metadata["needs_repair"] = True
                task.metadata["verification_failures"] = {
                    "syntax_errors": result.has_syntax_errors,
                    "compilation_errors": result.has_compilation_errors,
                    "test_failures": result.has_test_failures,
                }

    def _update_project_metrics(
        self, project_result: ProjectVerificationResult, task_result: TaskVerificationResult
    ) -> None:
        """Update project-level metrics from task results."""
        # Aggregate test metrics
        for artifact_results in task_result.artifact_results.values():
            for result in artifact_results:
                if result.verification_type == VerificationType.TEST:
                    project_result.total_tests_run += result.metrics.tests_total
                    project_result.total_tests_passed += result.metrics.tests_passed

                    # Track coverage
                    if result.metrics.coverage_percent > 0:
                        if project_result.overall_test_coverage is None:
                            project_result.overall_test_coverage = result.metrics.coverage_percent
                        else:
                            # Simple average (could be weighted by LOC in production)
                            project_result.overall_test_coverage = (
                                project_result.overall_test_coverage
                                + result.metrics.coverage_percent
                            ) / 2

    async def _create_syntax_repair_task(
        self, original_task_id: UUID, syntax_errors: list[tuple[UUID, VerificationResult]]
    ) -> Task:
        """Create a repair task for syntax errors."""
        # Consolidate error information
        error_details = []
        for artifact_id, result in syntax_errors:
            artifact = await self.artifact_manager.get_artifact(artifact_id)
            if artifact:
                error_details.append(
                    {
                        "artifact_name": artifact.name,
                        "errors": result.error_messages,
                        "suggestions": result.suggestions,
                    }
                )

        description = f"""Fix syntax errors in the following files:
{chr(10).join(f"- {e['artifact_name']}: {', '.join(e['errors'][:2])}" for e in error_details)}

Use the error messages and suggestions to correct the syntax issues."""

        return Task(
            id=uuid4(),
            name="Fix syntax errors",
            description=description,
            required_role=AgentRole.CODE_GENERATOR,
            priority=TaskPriority.HIGH,
            status=TaskStatus.PENDING,
            dependencies=[original_task_id],
            metadata={
                "repair_type": "syntax",
                "original_task": str(original_task_id),
                "error_details": error_details,
            },
        )

    async def _create_compilation_repair_task(
        self, original_task_id: UUID, compilation_errors: list[tuple[UUID, VerificationResult]]
    ) -> Task:
        """Create a repair task for compilation errors."""
        error_details = []
        for artifact_id, result in compilation_errors:
            artifact = await self.artifact_manager.get_artifact(artifact_id)
            if artifact:
                error_details.append(
                    {
                        "artifact_name": artifact.name,
                        "errors": result.error_messages,
                        "suggestions": result.suggestions,
                    }
                )

        description = f"""Fix compilation errors in the following files:
{chr(10).join(f"- {e['artifact_name']}: {', '.join(e['errors'][:2])}" for e in error_details)}

Ensure the code compiles successfully without errors."""

        return Task(
            id=uuid4(),
            name="Fix compilation errors",
            description=description,
            required_role=AgentRole.CODE_GENERATOR,
            priority=TaskPriority.HIGH,
            status=TaskStatus.PENDING,
            dependencies=[original_task_id],
            metadata={
                "repair_type": "compilation",
                "original_task": str(original_task_id),
                "error_details": error_details,
            },
        )

    async def _create_test_repair_task(
        self, original_task_id: UUID, test_failures: list[tuple[UUID, VerificationResult]]
    ) -> Task:
        """Create a repair task for test failures."""
        failure_details = []
        for artifact_id, result in test_failures:
            artifact = await self.artifact_manager.get_artifact(artifact_id)
            if artifact:
                failure_details.append(
                    {
                        "artifact_name": artifact.name,
                        "failed_tests": result.metrics.tests_failed,
                        "total_tests": result.metrics.tests_total,
                        "errors": result.error_messages[:3],  # First 3 errors
                    }
                )

        description = f"""Fix failing tests:
{chr(10).join(f"- {f['artifact_name']}: {f['failed_tests']}/{f['total_tests']} tests failing" for f in failure_details)}

Review the test failures and fix the implementation to make all tests pass."""

        return Task(
            id=uuid4(),
            name="Fix failing tests",
            description=description,
            required_role=AgentRole.CODE_GENERATOR,
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.PENDING,
            dependencies=[original_task_id],
            metadata={
                "repair_type": "test",
                "original_task": str(original_task_id),
                "failure_details": failure_details,
            },
        )


# Convenience functions for Meta Agent integration


async def create_verification_integration(meta_agent) -> VerificationIntegration:
    """Create a verification integration instance for a Meta Agent.

    Args:
        meta_agent: The Meta Agent instance

    Returns:
        Configured VerificationIntegration instance

    """
    # Get verification config from Meta Agent settings if available
    config = VerificationConfig()
    if hasattr(meta_agent, "settings") and hasattr(meta_agent.settings, "verification"):
        # Update config from settings
        pass

    return VerificationIntegration(
        artifact_manager=meta_agent.artifact_manager,
        task_manager=meta_agent.task_manager,
        config=config,
    )


async def verify_and_repair(meta_agent, task: Task) -> bool:
    """Verify a task and generate repair tasks if needed.

    Args:
        meta_agent: The Meta Agent instance
        task: The task to verify

    Returns:
        True if verification passed or repairs were generated

    """
    integration = await create_verification_integration(meta_agent)

    # Verify the task
    result = await integration.verify_task_artifacts(task)

    if result.success:
        logger.info(f"Task {task.id} passed all verifications")
        return True

    # Generate repair tasks
    repair_tasks = await integration.generate_repair_tasks(result)

    if repair_tasks:
        logger.info(f"Generated {len(repair_tasks)} repair tasks for task {task.id}")
        # Add repair tasks to task manager
        await meta_agent.task_manager.add_tasks(repair_tasks)
        return True

    return False
