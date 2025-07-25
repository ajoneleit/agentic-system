"""Result Processing for MetaAgent modularization.

This module handles aggregation, processing, and formatting of task results
and project artifacts for the MetaAgent system.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from structlog import get_logger

from src.core.artifact_manager import ArtifactManager
from src.core.exceptions import ResultProcessingError
from src.core.interfaces import Artifact, Task
from src.core.result import Result
from src.core.task_result import TaskResult

logger = get_logger(__name__)


class ResultProcessor:
    """Processes and aggregates task results and artifacts."""

    def __init__(self, artifact_manager: Optional[ArtifactManager] = None):
        """Initialize result processor.

        Args:
            artifact_manager: Optional artifact manager for artifact operations

        """
        self.artifact_manager = artifact_manager
        self._processing_stats = {
            "results_processed": 0,
            "artifacts_aggregated": 0,
            "errors_encountered": 0,
        }

        logger.info("Result processor initialized")

    async def aggregate_task_results(
        self, task_results: dict[UUID, TaskResult], tasks: list[Task]
    ) -> Result[dict[str, Any]]:
        """Aggregate task results into a comprehensive summary.

        Args:
            task_results: Dictionary mapping task IDs to results
            tasks: List of executed tasks

        Returns:
            Result containing aggregated summary or error

        """
        try:
            # Calculate basic statistics
            total_tasks = len(tasks)
            successful_tasks = sum(1 for result in task_results.values() if result.success)
            failed_tasks = total_tasks - successful_tasks
            success_rate = (successful_tasks / total_tasks * 100) if total_tasks > 0 else 0

            # Calculate execution metrics
            total_execution_time = sum(
                result.execution_time
                for result in task_results.values()
                if hasattr(result, "execution_time")
            )
            avg_execution_time = total_execution_time / total_tasks if total_tasks > 0 else 0

            # Collect all artifacts
            all_artifacts = []
            artifact_types = {}
            for result in task_results.values():
                if result.success and hasattr(result, "artifacts"):
                    for artifact in result.artifacts:
                        all_artifacts.append(artifact)
                        artifact_type = (
                            artifact.type.value if hasattr(artifact, "type") else "unknown"
                        )
                        artifact_types[artifact_type] = artifact_types.get(artifact_type, 0) + 1

            # Collect errors from failed tasks
            errors = []
            for task_id, result in task_results.items():
                if not result.success and hasattr(result, "errors"):
                    task_name = next((t.name for t in tasks if t.id == task_id), str(task_id))
                    for error in result.errors:
                        errors.append(
                            {"task_id": str(task_id), "task_name": task_name, "error": error}
                        )

            # Analyze task types
            task_type_distribution = {}
            for task in tasks:
                task_type = getattr(task, "type", "unknown")
                task_type_distribution[task_type] = task_type_distribution.get(task_type, 0) + 1

            # Analyze task roles
            role_distribution = {}
            for task in tasks:
                role = getattr(task, "required_role", None)
                if role:
                    role_name = role.value if hasattr(role, "value") else str(role)
                    role_distribution[role_name] = role_distribution.get(role_name, 0) + 1

            # Create comprehensive summary
            aggregated_results = {
                "execution_summary": {
                    "total_tasks": total_tasks,
                    "successful_tasks": successful_tasks,
                    "failed_tasks": failed_tasks,
                    "success_rate": round(success_rate, 2),
                    "total_execution_time": round(total_execution_time, 2),
                    "average_execution_time": round(avg_execution_time, 2),
                },
                "artifact_summary": {
                    "total_artifacts": len(all_artifacts),
                    "artifact_types": artifact_types,
                },
                "task_analysis": {
                    "task_type_distribution": task_type_distribution,
                    "role_distribution": role_distribution,
                },
                "errors": errors,
                "processing_timestamp": datetime.now(timezone.utc).isoformat(),
            }

            self._processing_stats["results_processed"] += 1
            self._processing_stats["artifacts_aggregated"] += len(all_artifacts)
            if errors:
                self._processing_stats["errors_encountered"] += len(errors)

            logger.info(
                "Task results aggregated successfully",
                total_tasks=total_tasks,
                success_rate=success_rate,
                total_artifacts=len(all_artifacts),
            )

            return Result.success(aggregated_results)

        except Exception as e:
            logger.error("Failed to aggregate task results", error=str(e), exc_info=True)
            return Result.failure(
                ResultProcessingError(f"Failed to aggregate task results: {str(e)}")
            )

    async def collect_project_artifacts(
        self, task_results: dict[UUID, TaskResult], project_id: str
    ) -> Result[list[Artifact]]:
        """Collect all artifacts from task results.

        Args:
            task_results: Dictionary of task results
            project_id: Project identifier for filtering

        Returns:
            Result containing list of artifacts or error

        """
        try:
            artifacts = []

            for task_id, result in task_results.items():
                if result.success and hasattr(result, "artifacts"):
                    for artifact in result.artifacts:
                        # Enhance artifact with project context if needed
                        if hasattr(artifact, "metadata"):
                            if not artifact.metadata:
                                artifact.metadata = {}
                            artifact.metadata["project_id"] = project_id
                            artifact.metadata["task_id"] = str(task_id)

                        artifacts.append(artifact)

            # If artifact manager is available, verify artifacts are stored
            if self.artifact_manager:
                verified_artifacts = []
                for artifact in artifacts:
                    try:
                        stored_artifact = await self.artifact_manager.get_artifact(artifact.id)
                        if stored_artifact:
                            verified_artifacts.append(stored_artifact)
                        else:
                            # Store the artifact if not already stored
                            stored_artifact = await self.artifact_manager.store_artifact(artifact)
                            verified_artifacts.append(stored_artifact)
                    except Exception as e:
                        logger.warning(
                            "Failed to verify/store artifact",
                            artifact_id=str(artifact.id),
                            error=str(e),
                        )
                        # Include original artifact even if storage failed
                        verified_artifacts.append(artifact)

                artifacts = verified_artifacts

            logger.info(
                "Project artifacts collected", project_id=project_id, artifact_count=len(artifacts)
            )

            return Result.success(artifacts)

        except Exception as e:
            logger.error("Failed to collect project artifacts", error=str(e))
            return Result.failure(ResultProcessingError(f"Failed to collect artifacts: {str(e)}"))

    async def generate_execution_report(
        self,
        task_results: dict[UUID, TaskResult],
        tasks: list[Task],
        project_id: str,
        user_request: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
    ) -> Result[dict[str, Any]]:
        """Generate comprehensive execution report.

        Args:
            task_results: Dictionary of task results
            tasks: List of executed tasks
            project_id: Project identifier
            user_request: Original user request
            start_time: Execution start time
            end_time: Execution end time (defaults to current time)

        Returns:
            Result containing execution report or error

        """
        try:
            if not end_time:
                end_time = datetime.now(timezone.utc)

            # Get aggregated results
            aggregation_result = await self.aggregate_task_results(task_results, tasks)
            if aggregation_result.is_failure():
                return Result.failure(aggregation_result.get_error())

            aggregated = aggregation_result.unwrap()

            # Collect artifacts
            artifacts_result = await self.collect_project_artifacts(task_results, project_id)
            if artifacts_result.is_failure():
                return Result.failure(artifacts_result.get_error())

            artifacts = artifacts_result.unwrap()

            # Create detailed task breakdown
            task_breakdown = []
            for task in tasks:
                task_id = task.id
                result = task_results.get(task_id)

                task_info = {
                    "id": str(task_id),
                    "name": task.name,
                    "type": getattr(task, "type", "unknown"),
                    "status": task.status.value if hasattr(task, "status") else "unknown",
                    "success": result.success if result else False,
                    "execution_time": (
                        result.execution_time if result and hasattr(result, "execution_time") else 0
                    ),
                    "artifact_count": (
                        len(result.artifacts) if result and hasattr(result, "artifacts") else 0
                    ),
                }

                if result and not result.success and hasattr(result, "errors"):
                    task_info["errors"] = result.errors

                task_breakdown.append(task_info)

            # Create file summary
            file_summary = {}
            for artifact in artifacts:
                if hasattr(artifact, "file_path") and artifact.file_path:
                    file_type = artifact.type.value if hasattr(artifact, "type") else "unknown"
                    file_size = (
                        len(artifact.content)
                        if hasattr(artifact, "content") and artifact.content
                        else 0
                    )

                    file_summary[artifact.file_path] = {
                        "type": file_type,
                        "size": file_size,
                        "artifact_id": str(artifact.id) if hasattr(artifact, "id") else "unknown",
                    }

            # Create comprehensive report
            execution_report = {
                "project_info": {
                    "id": project_id,
                    "request": user_request,
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "duration_seconds": (end_time - start_time).total_seconds(),
                },
                "execution_summary": aggregated["execution_summary"],
                "artifact_summary": {
                    **aggregated["artifact_summary"],
                    "files_created": list(file_summary.keys()),
                    "file_details": file_summary,
                },
                "task_analysis": aggregated["task_analysis"],
                "detailed_tasks": task_breakdown,
                "errors_and_warnings": aggregated["errors"],
                "performance_metrics": {
                    "tasks_per_second": aggregated["execution_summary"]["total_tasks"]
                    / max((end_time - start_time).total_seconds(), 1),
                    "average_task_time": aggregated["execution_summary"]["average_execution_time"],
                    "total_processing_time": aggregated["execution_summary"][
                        "total_execution_time"
                    ],
                },
                "metadata": {
                    "report_generated_at": datetime.now(timezone.utc).isoformat(),
                    "processor_version": "1.0",
                    "total_artifacts_processed": len(artifacts),
                },
            }

            logger.info(
                "Execution report generated",
                project_id=project_id,
                report_size=len(str(execution_report)),
            )

            return Result.success(execution_report)

        except Exception as e:
            logger.error("Failed to generate execution report", error=str(e), exc_info=True)
            return Result.failure(
                ResultProcessingError(f"Failed to generate execution report: {str(e)}")
            )

    async def create_result_summary(
        self, task_results: dict[UUID, TaskResult], tasks: list[Task]
    ) -> Result[str]:
        """Create a human-readable summary of results.

        Args:
            task_results: Dictionary of task results
            tasks: List of executed tasks

        Returns:
            Result containing formatted summary string or error

        """
        try:
            # Get aggregated results
            aggregation_result = await self.aggregate_task_results(task_results, tasks)
            if aggregation_result.is_failure():
                return Result.failure(aggregation_result.get_error())

            aggregated = aggregation_result.unwrap()
            summary = aggregated["execution_summary"]

            # Create formatted summary
            lines = [
                "🤖 AGENTIC SYSTEM EXECUTION SUMMARY",
                "=" * 50,
                f"📊 Tasks: {summary['total_tasks']} total, {summary['successful_tasks']} successful, {summary['failed_tasks']} failed",
                f"✅ Success Rate: {summary['success_rate']:.1f}%",
                f"⏱️  Execution Time: {summary['total_execution_time']:.2f}s total, {summary['average_execution_time']:.2f}s average",
                f"📁 Artifacts: {aggregated['artifact_summary']['total_artifacts']} created",
                "",
            ]

            # Add artifact type breakdown if available
            if aggregated["artifact_summary"]["artifact_types"]:
                lines.append("📝 Artifact Types:")
                for artifact_type, count in aggregated["artifact_summary"][
                    "artifact_types"
                ].items():
                    lines.append(f"   • {artifact_type}: {count}")
                lines.append("")

            # Add task type breakdown
            if aggregated["task_analysis"]["task_type_distribution"]:
                lines.append("🎯 Task Types:")
                for task_type, count in aggregated["task_analysis"][
                    "task_type_distribution"
                ].items():
                    lines.append(f"   • {task_type}: {count}")
                lines.append("")

            # Add errors if any
            if aggregated["errors"]:
                lines.append(f"❌ Errors ({len(aggregated['errors'])}):")
                for error in aggregated["errors"][:5]:  # Limit to first 5 errors
                    lines.append(f"   • {error['task_name']}: {error['error']}")
                if len(aggregated["errors"]) > 5:
                    lines.append(f"   • ... and {len(aggregated['errors']) - 5} more errors")
                lines.append("")

            lines.append(f"Generated at: {aggregated['processing_timestamp']}")

            summary_text = "\n".join(lines)

            logger.info("Result summary created", summary_length=len(summary_text))

            return Result.success(summary_text)

        except Exception as e:
            logger.error("Failed to create result summary", error=str(e))
            return Result.failure(
                ResultProcessingError(f"Failed to create result summary: {str(e)}")
            )

    def get_processing_stats(self) -> dict[str, Any]:
        """Get result processing statistics.

        Returns:
            Dictionary containing processing statistics

        """
        return self._processing_stats.copy()

    def reset_stats(self) -> None:
        """Reset processing statistics."""
        self._processing_stats = {
            "results_processed": 0,
            "artifacts_aggregated": 0,
            "errors_encountered": 0,
        }
        logger.info("Result processing statistics reset")

    async def validate_results(
        self, task_results: dict[UUID, TaskResult], tasks: list[Task]
    ) -> Result[dict[str, Any]]:
        """Validate task results for consistency and completeness.

        Args:
            task_results: Dictionary of task results
            tasks: List of executed tasks

        Returns:
            Result containing validation report or error

        """
        try:
            validation_report = {"is_valid": True, "issues": [], "warnings": [], "summary": {}}

            # Check if all tasks have results
            task_ids = {task.id for task in tasks}
            result_ids = set(task_results.keys())

            missing_results = task_ids - result_ids
            extra_results = result_ids - task_ids

            if missing_results:
                validation_report["is_valid"] = False
                validation_report["issues"].append(
                    {
                        "type": "missing_results",
                        "description": f"Missing results for {len(missing_results)} tasks",
                        "task_ids": [str(tid) for tid in missing_results],
                    }
                )

            if extra_results:
                validation_report["warnings"].append(
                    {
                        "type": "extra_results",
                        "description": f"Found results for {len(extra_results)} unknown tasks",
                        "task_ids": [str(tid) for tid in extra_results],
                    }
                )

            # Validate result consistency
            for task_id, result in task_results.items():
                if not hasattr(result, "success"):
                    validation_report["is_valid"] = False
                    validation_report["issues"].append(
                        {
                            "type": "malformed_result",
                            "description": f"Result for task {task_id} missing success field",
                            "task_id": str(task_id),
                        }
                    )

                # Check for results claiming success but having errors
                if (
                    hasattr(result, "success")
                    and result.success
                    and hasattr(result, "errors")
                    and result.errors
                ):
                    validation_report["warnings"].append(
                        {
                            "type": "success_with_errors",
                            "description": f"Task {task_id} marked as successful but has errors",
                            "task_id": str(task_id),
                            "error_count": len(result.errors),
                        }
                    )

            validation_report["summary"] = {
                "total_tasks": len(tasks),
                "total_results": len(task_results),
                "missing_results": len(missing_results),
                "extra_results": len(extra_results),
                "issues_found": len(validation_report["issues"]),
                "warnings_found": len(validation_report["warnings"]),
            }

            logger.info(
                "Results validation completed",
                is_valid=validation_report["is_valid"],
                issues=len(validation_report["issues"]),
                warnings=len(validation_report["warnings"]),
            )

            return Result.success(validation_report)

        except Exception as e:
            logger.error("Failed to validate results", error=str(e))
            return Result.failure(ResultProcessingError(f"Failed to validate results: {str(e)}"))
