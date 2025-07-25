"""Filesystem-based storage backend for artifacts.

This module provides persistent storage of artifacts on the filesystem
with compression support and atomic operations.
"""

import gzip
import json
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import aiofiles
import aiofiles.os
from structlog import get_logger

from src.core.interfaces import Artifact, ArtifactType

logger = get_logger(__name__)


class FilesystemStorage:
    """Filesystem-based storage for artifacts with compression support."""

    def __init__(
        self, base_path: Path, enable_compression: bool = True, compression_level: int = 6
    ):
        """Initialize filesystem storage.

        Args:
            base_path: Base directory for storage
            enable_compression: Whether to compress artifacts
            compression_level: gzip compression level (1-9)

        """
        self.base_path = Path(base_path).resolve()
        self.enable_compression = enable_compression
        self.compression_level = compression_level

        # Directory structure
        self.artifacts_dir = self.base_path / "artifacts"
        self.metadata_dir = self.base_path / "metadata"
        self.index_file = self.base_path / "index.json"

        logger.info(
            "FilesystemStorage initialized",
            base_path=str(self.base_path),
            compression=enable_compression,
        )

    async def initialize(self) -> None:
        """Initialize storage directories and indexes."""
        # Create directory structure
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        # Initialize index if it doesn't exist
        if not self.index_file.exists():
            await self._save_index({})

        logger.info("FilesystemStorage directories initialized")

    async def store(self, artifact: Artifact) -> None:
        """Store an artifact to filesystem.

        Args:
            artifact: Artifact to store

        """
        # Determine paths
        artifact_path = self._get_artifact_path(artifact.id, artifact.version)
        metadata_path = self._get_metadata_path(artifact.id, artifact.version)

        # Ensure parent directories exist
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)

        # Serialize artifact content
        content_data = {"content": artifact.content, "encoding": artifact.encoding}
        content_bytes = json.dumps(content_data).encode("utf-8")

        # Compress if enabled
        if self.enable_compression:
            content_bytes = gzip.compress(content_bytes, compresslevel=self.compression_level)

        # Write content atomically
        temp_path = artifact_path.with_suffix(".tmp")
        try:
            async with aiofiles.open(temp_path, "wb") as f:
                await f.write(content_bytes)

            # Atomic rename
            temp_path.replace(artifact_path)

        except Exception:
            # Clean up temp file on error
            if temp_path.exists():
                temp_path.unlink()
            raise

        # Store metadata
        metadata = self._serialize_metadata(artifact)
        await self._write_json(metadata_path, metadata)

        # Update index
        await self._update_index(artifact.id, artifact.version)

        logger.debug(
            "Artifact stored",
            artifact_id=str(artifact.id),
            version=artifact.version,
            size=len(content_bytes),
        )

    async def get(self, artifact_id: UUID, version: Optional[int] = None) -> Optional[Artifact]:
        """Retrieve an artifact from filesystem.

        Args:
            artifact_id: Artifact ID
            version: Specific version (latest if None)

        Returns:
            Retrieved artifact or None if not found

        """
        # Determine version if not specified
        if version is None:
            version = await self._get_latest_version(artifact_id)
            if version is None:
                return None

        # Get paths
        artifact_path = self._get_artifact_path(artifact_id, version)
        metadata_path = self._get_metadata_path(artifact_id, version)

        # Check existence
        if not artifact_path.exists() or not metadata_path.exists():
            return None

        # Load metadata
        metadata = await self._read_json(metadata_path)

        # Load content
        try:
            async with aiofiles.open(artifact_path, "rb") as f:
                content_bytes = await f.read()

            # Decompress if needed
            if self.enable_compression:
                content_bytes = gzip.decompress(content_bytes)

            # Deserialize content
            content_data = json.loads(content_bytes.decode("utf-8"))

            # Reconstruct artifact
            artifact = self._deserialize_artifact(metadata, content_data["content"])

            logger.debug("Artifact retrieved", artifact_id=str(artifact_id), version=version)

            return artifact

        except Exception as e:
            logger.error(
                "Failed to retrieve artifact",
                artifact_id=str(artifact_id),
                version=version,
                error=str(e),
            )
            return None

    async def delete(self, artifact_id: UUID, version: Optional[int] = None) -> None:
        """Delete an artifact from filesystem.

        Args:
            artifact_id: Artifact ID
            version: Specific version (all versions if None)

        """
        if version is None:
            # Delete all versions
            versions = await self._get_all_versions(artifact_id)
            for v in versions:
                await self._delete_version(artifact_id, v)
        else:
            # Delete specific version
            await self._delete_version(artifact_id, version)

        logger.info("Artifact deleted", artifact_id=str(artifact_id), version=version)

    async def list_artifacts(self) -> list[tuple[UUID, int]]:
        """List all stored artifacts.

        Returns:
            List of (artifact_id, version) tuples

        """
        index = await self._load_index()
        artifacts = []

        for artifact_id_str, versions in index.items():
            artifact_id = UUID(artifact_id_str)
            for version in versions:
                artifacts.append((artifact_id, version))

        return artifacts

    async def get_storage_info(self) -> dict[str, Any]:
        """Get storage statistics.

        Returns:
            Storage information and statistics

        """
        total_size = 0
        artifact_count = 0

        # Calculate total size
        for path in self.artifacts_dir.rglob("*.artifact*"):
            if path.is_file():
                total_size += path.stat().st_size
                artifact_count += 1

        # Get index size
        index = await self._load_index()
        unique_artifacts = len(index)

        return {
            "base_path": str(self.base_path),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "artifact_count": artifact_count,
            "unique_artifacts": unique_artifacts,
            "compression_enabled": self.enable_compression,
        }

    async def load_metadata(self) -> list[dict[str, Any]]:
        """Load all artifact metadata for indexing.

        Returns:
            List of metadata dictionaries

        """
        metadata_list = []

        # Scan metadata directory
        for metadata_path in self.metadata_dir.rglob("*.meta.json"):
            try:
                metadata = await self._read_json(metadata_path)
                metadata_list.append(metadata)
            except Exception as e:
                logger.warning("Failed to load metadata", path=str(metadata_path), error=str(e))

        return metadata_list

    def _get_artifact_path(self, artifact_id: UUID, version: int) -> Path:
        """Get filesystem path for an artifact."""
        # Use first 2 chars of UUID for sharding
        shard = str(artifact_id)[:2]
        filename = f"{artifact_id}_v{version}.artifact"

        if self.enable_compression:
            filename += ".gz"

        return self.artifacts_dir / shard / filename

    def _get_metadata_path(self, artifact_id: UUID, version: int) -> Path:
        """Get filesystem path for artifact metadata."""
        shard = str(artifact_id)[:2]
        filename = f"{artifact_id}_v{version}.meta.json"
        return self.metadata_dir / shard / filename

    async def _get_latest_version(self, artifact_id: UUID) -> Optional[int]:
        """Get the latest version number for an artifact."""
        index = await self._load_index()
        versions = index.get(str(artifact_id), [])
        return max(versions) if versions else None

    async def _get_all_versions(self, artifact_id: UUID) -> list[int]:
        """Get all version numbers for an artifact."""
        index = await self._load_index()
        return index.get(str(artifact_id), [])

    async def _delete_version(self, artifact_id: UUID, version: int) -> None:
        """Delete a specific version."""
        artifact_path = self._get_artifact_path(artifact_id, version)
        metadata_path = self._get_metadata_path(artifact_id, version)

        # Delete files
        if artifact_path.exists():
            artifact_path.unlink()
        if metadata_path.exists():
            metadata_path.unlink()

        # Update index
        index = await self._load_index()
        if str(artifact_id) in index:
            versions = index[str(artifact_id)]
            if version in versions:
                versions.remove(version)
            if not versions:
                del index[str(artifact_id)]
            await self._save_index(index)

    async def _load_index(self) -> dict[str, list[int]]:
        """Load the artifact index."""
        if not self.index_file.exists():
            return {}

        return await self._read_json(self.index_file)

    async def _save_index(self, index: dict[str, list[int]]) -> None:
        """Save the artifact index."""
        await self._write_json(self.index_file, index)

    async def _update_index(self, artifact_id: UUID, version: int) -> None:
        """Update index with new artifact version."""
        index = await self._load_index()

        artifact_id_str = str(artifact_id)
        if artifact_id_str not in index:
            index[artifact_id_str] = []

        if version not in index[artifact_id_str]:
            index[artifact_id_str].append(version)
            index[artifact_id_str].sort()

        await self._save_index(index)

    async def _write_json(self, path: Path, data: Any) -> None:
        """Write JSON data to file atomically."""
        temp_path = path.with_suffix(".tmp")

        try:
            async with aiofiles.open(temp_path, "w") as f:
                await f.write(json.dumps(data, indent=2, default=str))

            # Atomic rename
            temp_path.replace(path)

        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    async def _read_json(self, path: Path) -> Any:
        """Read JSON data from file."""
        async with aiofiles.open(path) as f:
            content = await f.read()
        return json.loads(content)

    def _serialize_metadata(self, artifact: Artifact) -> dict[str, Any]:
        """Serialize artifact metadata to dictionary."""
        return {
            "id": str(artifact.id),
            "name": artifact.name,
            "type": artifact.type.value,
            "version": artifact.version,
            "language": artifact.language,
            "path": str(artifact.path) if artifact.path else None,
            "created_at": artifact.created_at.isoformat(),
            "modified_at": artifact.modified_at.isoformat(),
            "task_id": str(artifact.task_id),
            "agent_id": str(artifact.agent_id),
            "previous_version_id": (
                str(artifact.previous_version_id) if artifact.previous_version_id else None
            ),
            "checksum": artifact.checksum,
            "size_bytes": artifact.size_bytes,
            "encoding": artifact.encoding,
            "dependencies": [str(d) for d in artifact.dependencies],
            "tags": list(artifact.tags),
            "metadata": artifact.metadata,
        }

    def _deserialize_artifact(self, metadata: dict[str, Any], content: str) -> Artifact:
        """Deserialize artifact from metadata and content."""
        # Parse dates
        from datetime import datetime

        created_at = datetime.fromisoformat(metadata["created_at"])
        modified_at = datetime.fromisoformat(metadata["modified_at"])

        # Parse UUIDs
        artifact_id = UUID(metadata["id"])
        task_id = UUID(metadata["task_id"])
        agent_id = UUID(metadata["agent_id"])
        prev_version_id = (
            UUID(metadata["previous_version_id"]) if metadata.get("previous_version_id") else None
        )
        dependencies = [UUID(d) for d in metadata.get("dependencies", [])]

        # Create artifact
        artifact = Artifact(
            id=artifact_id,
            name=metadata["name"],
            type=ArtifactType(metadata["type"]),
            content=content,
            language=metadata.get("language"),
            path=Path(metadata["path"]) if metadata.get("path") else None,
            version=metadata["version"],
            created_at=created_at,
            modified_at=modified_at,
            task_id=task_id,
            agent_id=agent_id,
            previous_version_id=prev_version_id,
            checksum=metadata.get("checksum"),
            size_bytes=metadata.get("size_bytes", 0),
            encoding=metadata.get("encoding", "utf-8"),
            dependencies=set(dependencies),
            tags=set(metadata.get("tags", [])),
            metadata=metadata.get("metadata", {}),
        )

        return artifact
