"""Artifact factory for creating different types of artifacts.

This module provides a factory pattern for creating artifacts with
proper metadata and validation.
"""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from structlog import get_logger

from src.core.exceptions import ArtifactError
from src.core.interfaces import Artifact, ArtifactType, Task
from src.core.result import Result

logger = get_logger(__name__)


class ArtifactFactory:
    """Factory for creating different types of artifacts."""

    def __init__(self, project_id: str, workspace_path: Path):
        """Initialize the artifact factory.

        Args:
            project_id: Project identifier
            workspace_path: Path to the workspace directory

        """
        self.project_id = project_id
        self.workspace_path = workspace_path
        self._artifact_counter = 0

    def create_code_artifact(
        self,
        content: str,
        filename: str,
        task: Task,
        language: str = "python",
        metadata: Optional[dict[str, Any]] = None,
    ) -> Result[Artifact]:
        """Create a code artifact.

        Args:
            content: The code content
            filename: Name of the file
            task: Task that generated this artifact
            language: Programming language
            metadata: Additional metadata

        Returns:
            Result containing code artifact or error

        """
        try:
            # Validate content
            if not content.strip():
                return Result.failure(ArtifactError("Code content cannot be empty"))

            # Ensure proper file extension
            if not filename.endswith(self._get_language_extension(language)):
                filename += self._get_language_extension(language)

            # Create base metadata
            artifact_metadata = {
                "language": language,
                "task_id": str(task.id),
                "task_name": task.name,
                "task_type": task.type,
                "generated_by": "code_generator",
                "line_count": len(content.split("\n")),
                "character_count": len(content),
                **(metadata or {}),
            }

            # Create artifact
            artifact = Artifact(
                id=uuid4(),
                name=filename,
                type=ArtifactType.SOURCE_CODE,
                content=content,
                file_path=filename,
                created_at=datetime.now(timezone.utc),
                checksum=self._calculate_checksum(content),
                metadata=artifact_metadata,
                task_id=task.id,
                project_id=self.project_id,
            )

            logger.info(
                "Code artifact created",
                artifact_id=str(artifact.id),
                filename=filename,
                language=language,
                size=len(content),
            )

            return Result.success(artifact)

        except Exception as e:
            logger.error("Failed to create code artifact", error=str(e), exc_info=True)
            return Result.failure(ArtifactError(f"Failed to create code artifact: {str(e)}"))

    def create_test_artifact(
        self,
        content: str,
        filename: str,
        task: Task,
        test_framework: str = "pytest",
        tested_modules: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Result[Artifact]:
        """Create a test artifact.

        Args:
            content: The test code content
            filename: Name of the test file
            task: Task that generated this artifact
            test_framework: Testing framework used
            tested_modules: List of modules being tested
            metadata: Additional metadata

        Returns:
            Result containing test artifact or error

        """
        try:
            # Validate content
            if not content.strip():
                return Result.failure(ArtifactError("Test content cannot be empty"))

            # Ensure proper test file naming
            if not filename.startswith("test_") and not filename.endswith("_test.py"):
                filename = f"test_{filename}"
            if not filename.endswith(".py"):
                filename += ".py"

            # Analyze test content
            test_functions = self._count_test_functions(content)

            # Create base metadata
            artifact_metadata = {
                "test_framework": test_framework,
                "tested_modules": tested_modules or [],
                "test_function_count": test_functions,
                "task_id": str(task.id),
                "task_name": task.name,
                "task_type": task.type,
                "generated_by": "test_generator",
                "line_count": len(content.split("\n")),
                "character_count": len(content),
                **(metadata or {}),
            }

            # Create artifact
            artifact = Artifact(
                id=uuid4(),
                name=filename,
                type=ArtifactType.TEST_CODE,
                content=content,
                file_path=filename,
                created_at=datetime.now(timezone.utc),
                checksum=self._calculate_checksum(content),
                metadata=artifact_metadata,
                task_id=task.id,
                project_id=self.project_id,
            )

            logger.info(
                "Test artifact created",
                artifact_id=str(artifact.id),
                filename=filename,
                test_framework=test_framework,
                test_count=test_functions,
            )

            return Result.success(artifact)

        except Exception as e:
            logger.error("Failed to create test artifact", error=str(e), exc_info=True)
            return Result.failure(ArtifactError(f"Failed to create test artifact: {str(e)}"))

    def create_documentation_artifact(
        self,
        content: str,
        filename: str,
        task: Task,
        doc_type: str = "markdown",
        documented_modules: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Result[Artifact]:
        """Create a documentation artifact.

        Args:
            content: The documentation content
            filename: Name of the documentation file
            task: Task that generated this artifact
            doc_type: Type of documentation (markdown, rst, etc.)
            documented_modules: List of modules being documented
            metadata: Additional metadata

        Returns:
            Result containing documentation artifact or error

        """
        try:
            # Validate content
            if not content.strip():
                return Result.failure(ArtifactError("Documentation content cannot be empty"))

            # Ensure proper file extension
            if doc_type == "markdown" and not filename.endswith(".md"):
                filename += ".md"
            elif doc_type == "rst" and not filename.endswith(".rst"):
                filename += ".rst"

            # Analyze documentation content
            sections = self._count_documentation_sections(content)

            # Create base metadata
            artifact_metadata = {
                "doc_type": doc_type,
                "documented_modules": documented_modules or [],
                "section_count": sections,
                "task_id": str(task.id),
                "task_name": task.name,
                "task_type": task.type,
                "generated_by": "documentation_generator",
                "line_count": len(content.split("\n")),
                "character_count": len(content),
                **(metadata or {}),
            }

            # Create artifact
            artifact = Artifact(
                id=uuid4(),
                name=filename,
                type=ArtifactType.DOCUMENTATION,
                content=content,
                file_path=filename,
                created_at=datetime.now(timezone.utc),
                checksum=self._calculate_checksum(content),
                metadata=artifact_metadata,
                task_id=task.id,
                project_id=self.project_id,
            )

            logger.info(
                "Documentation artifact created",
                artifact_id=str(artifact.id),
                filename=filename,
                doc_type=doc_type,
                sections=sections,
            )

            return Result.success(artifact)

        except Exception as e:
            logger.error("Failed to create documentation artifact", error=str(e), exc_info=True)
            return Result.failure(
                ArtifactError(f"Failed to create documentation artifact: {str(e)}")
            )

    def create_configuration_artifact(
        self,
        content: str,
        filename: str,
        task: Task,
        config_type: str = "json",
        metadata: Optional[dict[str, Any]] = None,
    ) -> Result[Artifact]:
        """Create a configuration artifact.

        Args:
            content: The configuration content
            filename: Name of the configuration file
            task: Task that generated this artifact
            config_type: Type of configuration (json, yaml, toml, etc.)
            metadata: Additional metadata

        Returns:
            Result containing configuration artifact or error

        """
        try:
            # Validate content
            if not content.strip():
                return Result.failure(ArtifactError("Configuration content cannot be empty"))

            # Ensure proper file extension
            extension_map = {
                "json": ".json",
                "yaml": ".yaml",
                "yml": ".yml",
                "toml": ".toml",
                "ini": ".ini",
            }

            extension = extension_map.get(config_type, f".{config_type}")
            if not filename.endswith(extension):
                filename += extension

            # Validate configuration format
            validation_result = self._validate_configuration_content(content, config_type)
            if validation_result.is_failure():
                return validation_result

            # Create base metadata
            artifact_metadata = {
                "config_type": config_type,
                "task_id": str(task.id),
                "task_name": task.name,
                "task_type": task.type,
                "generated_by": "configuration_generator",
                "line_count": len(content.split("\n")),
                "character_count": len(content),
                **(metadata or {}),
            }

            # Create artifact
            artifact = Artifact(
                id=uuid4(),
                name=filename,
                type=ArtifactType.CONFIGURATION,
                content=content,
                file_path=filename,
                created_at=datetime.now(timezone.utc),
                checksum=self._calculate_checksum(content),
                metadata=artifact_metadata,
                task_id=task.id,
                project_id=self.project_id,
            )

            logger.info(
                "Configuration artifact created",
                artifact_id=str(artifact.id),
                filename=filename,
                config_type=config_type,
            )

            return Result.success(artifact)

        except Exception as e:
            logger.error("Failed to create configuration artifact", error=str(e), exc_info=True)
            return Result.failure(
                ArtifactError(f"Failed to create configuration artifact: {str(e)}")
            )

    def create_generic_artifact(
        self,
        content: str,
        filename: str,
        task: Task,
        artifact_type: ArtifactType,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Result[Artifact]:
        """Create a generic artifact.

        Args:
            content: The artifact content
            filename: Name of the file
            task: Task that generated this artifact
            artifact_type: Type of artifact
            metadata: Additional metadata

        Returns:
            Result containing artifact or error

        """
        try:
            # Validate content
            if not content.strip():
                return Result.failure(ArtifactError("Artifact content cannot be empty"))

            # Create base metadata
            artifact_metadata = {
                "task_id": str(task.id),
                "task_name": task.name,
                "task_type": task.type,
                "generated_by": "generic_generator",
                "line_count": len(content.split("\n")),
                "character_count": len(content),
                **(metadata or {}),
            }

            # Create artifact
            artifact = Artifact(
                id=uuid4(),
                name=filename,
                type=artifact_type,
                content=content,
                file_path=filename,
                created_at=datetime.now(timezone.utc),
                checksum=self._calculate_checksum(content),
                metadata=artifact_metadata,
                task_id=task.id,
                project_id=self.project_id,
            )

            logger.info(
                "Generic artifact created",
                artifact_id=str(artifact.id),
                filename=filename,
                artifact_type=artifact_type.value,
            )

            return Result.success(artifact)

        except Exception as e:
            logger.error("Failed to create generic artifact", error=str(e), exc_info=True)
            return Result.failure(ArtifactError(f"Failed to create generic artifact: {str(e)}"))

    def _get_language_extension(self, language: str) -> str:
        """Get file extension for programming language.

        Args:
            language: Programming language

        Returns:
            File extension

        """
        extension_map = {
            "python": ".py",
            "javascript": ".js",
            "typescript": ".ts",
            "java": ".java",
            "cpp": ".cpp",
            "c": ".c",
            "go": ".go",
            "rust": ".rs",
            "ruby": ".rb",
            "php": ".php",
            "csharp": ".cs",
            "shell": ".sh",
            "powershell": ".ps1",
        }

        return extension_map.get(language.lower(), ".txt")

    def _count_test_functions(self, content: str) -> int:
        """Count test functions in content.

        Args:
            content: Test code content

        Returns:
            Number of test functions

        """
        lines = content.split("\n")
        count = 0

        for line in lines:
            stripped = line.strip()
            if (
                stripped.startswith("def test_")
                or stripped.startswith("async def test_")
                or stripped.startswith("function test")
            ):
                count += 1

        return count

    def _count_documentation_sections(self, content: str) -> int:
        """Count documentation sections.

        Args:
            content: Documentation content

        Returns:
            Number of sections

        """
        lines = content.split("\n")
        count = 0

        for line in lines:
            stripped = line.strip()
            # Count markdown headers
            if stripped.startswith("#") or stripped.startswith("=") or stripped.startswith("-"):
                count += 1

        return count

    def _validate_configuration_content(self, content: str, config_type: str) -> Result[None]:
        """Validate configuration content format.

        Args:
            content: Configuration content
            config_type: Type of configuration

        Returns:
            Result indicating validation success or failure

        """
        try:
            if config_type == "json":
                import json

                json.loads(content)
            elif config_type in ["yaml", "yml"]:
                import yaml

                yaml.safe_load(content)
            elif config_type == "toml":
                import tomli

                tomli.loads(content)
            # Add more validation as needed

            return Result.success(None)

        except Exception as e:
            return Result.failure(ArtifactError(f"Invalid {config_type} format: {str(e)}"))

    def _calculate_checksum(self, content: str) -> str:
        """Calculate SHA256 checksum of content.

        Args:
            content: Content to checksum

        Returns:
            Hex digest of checksum

        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get_workspace_path(self) -> Path:
        """Get workspace path for this factory.

        Returns:
            Workspace path

        """
        return self.workspace_path

    def get_project_id(self) -> str:
        """Get project ID for this factory.

        Returns:
            Project ID

        """
        return self.project_id
