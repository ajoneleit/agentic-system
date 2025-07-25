"""Project management and storage module.

This module provides the ProjectManager class that handles project storage,
lifecycle management, and artifact organization.
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from structlog import get_logger

from src.core.exceptions import ProjectError, StorageError
from src.core.interfaces import Artifact, ArtifactType
from src.core.result import Result
from src.core.task_result import TaskResult
from src.utils.app_logging import log_execution_time

logger = get_logger(__name__)


class ProjectManager:
    """Handles project storage and lifecycle management."""

    def __init__(self, base_storage_path: Path, artifact_manager=None):
        """Initialize the project manager.

        Args:
            base_storage_path: Base path for project storage
            artifact_manager: Artifact manager instance

        """
        self.base_storage_path = base_storage_path
        self.artifact_manager = artifact_manager
        self._project_cache: dict[str, dict[str, Any]] = {}

    @log_execution_time("initialize_project_storage")
    async def initialize_project_storage(
        self, user_request: str, project_id: Optional[str] = None
    ) -> Result[str]:
        """Initialize project storage and create project directory.

        Args:
            user_request: The user's original request
            project_id: Optional project ID, generates one if not provided

        Returns:
            Result containing project ID or error

        """
        try:
            if not project_id:
                project_id = self._generate_project_id(user_request)

            project_path = self.base_storage_path / "projects" / project_id

            # Create project directory structure
            await self._create_project_directories(project_path)

            # Create project metadata
            metadata = {
                "id": project_id,
                "request": user_request,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "in_progress",
                "artifacts": [],
                "tasks": [],
                "version": "1.0",
            }

            # Save metadata
            metadata_path = project_path / "project_metadata.json"
            await self._save_json_file(metadata_path, metadata)

            # Cache project info
            self._project_cache[project_id] = metadata

            logger.info(
                "Project storage initialized", project_id=project_id, path=str(project_path)
            )

            return Result.success(project_id)

        except Exception as e:
            logger.error("Project storage initialization failed", error=str(e), exc_info=True)
            return Result.failure(ProjectError(f"Failed to initialize project storage: {str(e)}"))

    async def _create_project_directories(self, project_path: Path) -> None:
        """Create the project directory structure.

        Args:
            project_path: Path to the project directory

        """
        directories = [
            project_path,
            project_path / "workspace",
            project_path / "artifacts",
            project_path / "logs",
            project_path / "temp",
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def _generate_project_id(self, user_request: str) -> str:
        """Generate a project ID based on the user request.

        Args:
            user_request: The user's request

        Returns:
            Generated project ID

        """
        # Extract meaningful words from request
        words = user_request.lower().split()
        meaningful_words = [word for word in words if len(word) > 3 and word.isalpha()][
            :3
        ]  # Take first 3 meaningful words

        if meaningful_words:
            base_name = "_".join(meaningful_words)
        else:
            base_name = "project"

        # Add timestamp for uniqueness
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{base_name}_{timestamp}"

    async def create_project_manifest(
        self, request: str, results: dict[str, TaskResult]
    ) -> Result[Artifact]:
        """Create a project manifest with execution results.

        Args:
            request: The original user request
            results: Dictionary of task results

        Returns:
            Result containing project manifest artifact or error

        """
        try:
            # Calculate project statistics
            total_tasks = len(results)
            successful_tasks = sum(1 for result in results.values() if result.is_success())
            total_artifacts = sum(
                len(result.unwrap().artifacts) for result in results.values() if result.is_success()
            )

            # Create manifest content
            manifest = {
                "project_info": {
                    "request": request,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "status": "completed" if successful_tasks == total_tasks else "partial",
                    "success_rate": (
                        (successful_tasks / total_tasks) * 100 if total_tasks > 0 else 0
                    ),
                },
                "execution_summary": {
                    "total_tasks": total_tasks,
                    "successful_tasks": successful_tasks,
                    "failed_tasks": total_tasks - successful_tasks,
                    "total_artifacts": total_artifacts,
                },
                "task_results": [],
                "artifacts": [],
                "generated_files": [],
            }

            # Add task results
            for task_id, result in results.items():
                if result.is_success():
                    task_result = result.unwrap()
                    task_info = {
                        "task_id": str(task_id),
                        "success": task_result.success,
                        "execution_time": task_result.execution_time,
                        "error": (
                            task_result.errors[0]
                            if not task_result.success and task_result.errors
                            else None
                        ),
                        "artifact_count": len(task_result.artifacts) if task_result.success else 0,
                    }
                    manifest["task_results"].append(task_info)

                    # Add artifacts
                    if task_result.success:
                        for artifact in task_result.artifacts:
                            artifact_info = {
                                "id": str(artifact.id),
                                "type": artifact.type.value,
                                "name": artifact.name,
                                "file_path": artifact.file_path,
                                "size": len(artifact.content) if artifact.content else 0,
                                "created_at": (
                                    artifact.created_at.isoformat() if artifact.created_at else None
                                ),
                            }
                            manifest["artifacts"].append(artifact_info)

                            # Add to generated files list
                            if artifact.file_path:
                                manifest["generated_files"].append(
                                    {
                                        "path": artifact.file_path,
                                        "type": artifact.type.value,
                                        "size": len(artifact.content) if artifact.content else 0,
                                    }
                                )
                else:
                    # Handle failed result
                    error = result.get_error()
                    task_info = {
                        "task_id": str(task_id),
                        "success": False,
                        "execution_time": 0,
                        "error": str(error) if error else "Unknown error",
                        "artifact_count": 0,
                    }
                    manifest["task_results"].append(task_info)

            # Create manifest artifact
            manifest_content = json.dumps(manifest, indent=2)
            manifest_artifact = Artifact(
                id=uuid4(),
                name="project_manifest.json",
                path=Path("project_manifest.json"),
                type=ArtifactType.CONFIGURATION,
                content=manifest_content,
                task_id=uuid4(),  # Use a dummy task ID for the manifest
                agent_id=uuid4(),  # Use a dummy agent ID for the manifest
                created_at=datetime.now(timezone.utc),
                checksum=self._calculate_checksum(manifest_content),
            )

            logger.info(
                "Project manifest created",
                total_tasks=total_tasks,
                successful_tasks=successful_tasks,
                artifact_count=total_artifacts,
            )

            return Result.success(manifest_artifact)

        except Exception as e:
            logger.error("Project manifest creation failed", error=str(e), exc_info=True)
            return Result.failure(ProjectError(f"Failed to create project manifest: {str(e)}"))

    async def store_execution_artifacts(
        self, project_id: str, results: dict[str, TaskResult]
    ) -> Result[None]:
        """Store execution artifacts in project directory.

        Args:
            project_id: The project identifier
            results: Dictionary of task results

        Returns:
            Result indicating success or error

        """
        try:
            project_path = self.base_storage_path / "projects" / project_id
            if not project_path.exists():
                return Result.failure(ProjectError(f"Project directory not found: {project_id}"))

            workspace_path = project_path / "workspace"
            artifacts_stored = 0

            # Store artifacts from successful tasks
            for _task_id, result in results.items():
                if result.is_success():
                    task_result = result.unwrap()
                    if task_result.success:
                        for artifact in task_result.artifacts:
                            if artifact.file_path and artifact.content:
                                file_path = workspace_path / artifact.file_path

                                # Create parent directories if needed
                                file_path.parent.mkdir(parents=True, exist_ok=True)

                                # Write artifact content
                                await self._write_file(file_path, artifact.content)
                                artifacts_stored += 1

                                # Store artifact metadata if artifact manager is available
                                if self.artifact_manager:
                                    await self.artifact_manager.store_artifact(artifact)

            # Update project metadata
            await self._update_project_metadata(
                project_id,
                {
                    "artifacts_stored": artifacts_stored,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "status": "completed",
                },
            )

            logger.info(
                "Execution artifacts stored",
                project_id=project_id,
                artifacts_stored=artifacts_stored,
            )

            return Result.success(None)

        except Exception as e:
            logger.error("Artifact storage failed", error=str(e), exc_info=True)
            return Result.failure(StorageError(f"Failed to store execution artifacts: {str(e)}"))

    async def get_project_info(self, project_id: str) -> Result[dict[str, Any]]:
        """Get project information.

        Args:
            project_id: The project identifier

        Returns:
            Result containing project information or error

        """
        try:
            # Check cache first
            if project_id in self._project_cache:
                return Result.success(self._project_cache[project_id])

            # Load from disk
            project_path = self.base_storage_path / "projects" / project_id
            metadata_path = project_path / "project_metadata.json"

            if not metadata_path.exists():
                return Result.failure(ProjectError(f"Project not found: {project_id}"))

            metadata = await self._load_json_file(metadata_path)
            self._project_cache[project_id] = metadata

            return Result.success(metadata)

        except Exception as e:
            logger.error("Failed to get project info", error=str(e), project_id=project_id)
            return Result.failure(ProjectError(f"Failed to get project info: {str(e)}"))

    async def list_projects(self, limit: int = 50) -> Result[list[dict[str, Any]]]:
        """List all projects.

        Args:
            limit: Maximum number of projects to return

        Returns:
            Result containing list of project information or error

        """
        try:
            projects_path = self.base_storage_path / "projects"
            if not projects_path.exists():
                return Result.success([])

            projects = []
            for project_dir in projects_path.iterdir():
                if project_dir.is_dir():
                    project_info_result = await self.get_project_info(project_dir.name)
                    if project_info_result.is_success():
                        projects.append(project_info_result.value)

                    if len(projects) >= limit:
                        break

            # Sort by creation date (most recent first)
            projects.sort(key=lambda p: p.get("created_at", ""), reverse=True)

            return Result.success(projects)

        except Exception as e:
            logger.error("Failed to list projects", error=str(e))
            return Result.failure(ProjectError(f"Failed to list projects: {str(e)}"))

    async def delete_project(self, project_id: str) -> Result[None]:
        """Delete a project and all its artifacts.

        Args:
            project_id: The project identifier

        Returns:
            Result indicating success or error

        """
        try:
            project_path = self.base_storage_path / "projects" / project_id
            if not project_path.exists():
                return Result.failure(ProjectError(f"Project not found: {project_id}"))

            # Remove from cache
            if project_id in self._project_cache:
                del self._project_cache[project_id]

            # Delete project directory
            import shutil

            shutil.rmtree(project_path)

            logger.info("Project deleted", project_id=project_id)
            return Result.success(None)

        except Exception as e:
            logger.error("Failed to delete project", error=str(e), project_id=project_id)
            return Result.failure(ProjectError(f"Failed to delete project: {str(e)}"))

    async def _save_json_file(self, path: Path, data: dict[str, Any]) -> None:
        """Save data to JSON file.

        Args:
            path: File path
            data: Data to save

        """
        async with asyncio.Lock():
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    async def _load_json_file(self, path: Path) -> dict[str, Any]:
        """Load data from JSON file.

        Args:
            path: File path

        Returns:
            Loaded data

        """
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    async def _write_file(self, path: Path, content: str) -> None:
        """Write content to file.

        Args:
            path: File path
            content: Content to write

        """
        async with asyncio.Lock():
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

    async def _update_project_metadata(self, project_id: str, updates: dict[str, Any]) -> None:
        """Update project metadata.

        Args:
            project_id: The project identifier
            updates: Updates to apply

        """
        project_path = self.base_storage_path / "projects" / project_id
        metadata_path = project_path / "project_metadata.json"

        if metadata_path.exists():
            metadata = await self._load_json_file(metadata_path)
            metadata.update(updates)
            await self._save_json_file(metadata_path, metadata)

            # Update cache
            self._project_cache[project_id] = metadata

    def _calculate_checksum(self, content: str) -> str:
        """Calculate SHA256 checksum of content.

        Args:
            content: Content to checksum

        Returns:
            Hex digest of checksum

        """
        import hashlib

        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def clear_cache(self) -> None:
        """Clear the project cache."""
        self._project_cache.clear()
        logger.info("Project cache cleared")
