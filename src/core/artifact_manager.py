"""Centralized artifact management system for the Agentic Coding System.

This module provides thread-safe, async-compatible artifact storage with
versioning, caching, and comprehensive error handling.
"""

import asyncio
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

from structlog import get_logger

from src.core.exceptions import AgenticSystemError
from src.core.interfaces import Artifact, ArtifactType
from src.storage.filesystem_storage import FilesystemStorage
from src.storage.memory_storage import MemoryStorage
from src.utils.file_manager import FileManager

logger = get_logger(__name__)


class ArtifactError(AgenticSystemError):
    """Base exception for artifact-related errors."""
    pass


class ArtifactNotFoundError(ArtifactError):
    """Raised when an artifact cannot be found."""
    
    def __init__(self, artifact_id: UUID):
        super().__init__(
            f"Artifact not found: {artifact_id}",
            error_code="ARTIFACT_NOT_FOUND",
            details={"artifact_id": str(artifact_id)}
        )


class VersionConflictError(ArtifactError):
    """Raised when there's a version conflict during artifact update."""
    
    def __init__(self, artifact_id: UUID, expected_version: int, actual_version: int):
        super().__init__(
            f"Version conflict for artifact {artifact_id}: expected {expected_version}, got {actual_version}",
            error_code="VERSION_CONFLICT",
            details={
                "artifact_id": str(artifact_id),
                "expected_version": expected_version,
                "actual_version": actual_version
            }
        )


class StorageError(ArtifactError):
    """Raised when storage operations fail."""
    pass


class CorruptionError(ArtifactError):
    """Raised when artifact data is corrupted."""
    pass


class ArtifactManager:
    """Manages all artifacts in the system with versioning and caching.
    
    Provides thread-safe operations for storing, retrieving, and managing
    code artifacts with comprehensive versioning support.
    """
    
    def __init__(
        self,
        storage_path: Path,
        max_memory_cache_size: int = 100,
        enable_compression: bool = True,
        auto_cleanup_days: int = 30
    ):
        """Initialize the artifact manager.
        
        Args:
            storage_path: Base path for artifact storage
            max_memory_cache_size: Maximum number of artifacts to cache in memory
            enable_compression: Whether to compress artifacts on disk
            auto_cleanup_days: Days to keep old versions before cleanup
        """
        self.storage_path = storage_path
        self.max_memory_cache_size = max_memory_cache_size
        self.enable_compression = enable_compression
        self.auto_cleanup_days = auto_cleanup_days
        
        # Storage backends
        self._memory_storage = MemoryStorage(max_size=max_memory_cache_size)
        self._filesystem_storage = FilesystemStorage(
            base_path=storage_path,
            enable_compression=enable_compression
        )
        self._file_manager = FileManager(storage_path)
        
        # Indexes for fast lookup
        self._artifacts_by_id: Dict[UUID, Artifact] = {}
        self._artifacts_by_name: Dict[str, List[UUID]] = defaultdict(list)
        self._artifacts_by_task: Dict[UUID, List[UUID]] = defaultdict(list)
        self._artifacts_by_agent: Dict[UUID, List[UUID]] = defaultdict(list)
        self._version_chains: Dict[UUID, List[UUID]] = defaultdict(list)
        
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
        
        # Metrics
        self._metrics = {
            "total_artifacts": 0,
            "total_versions": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "storage_operations": 0
        }
        
        logger.info(
            "ArtifactManager initialized",
            storage_path=str(storage_path),
            max_cache_size=max_memory_cache_size,
            compression_enabled=enable_compression
        )
    
    async def initialize(self) -> None:
        """Initialize storage backends and load metadata."""
        await self._filesystem_storage.initialize()
        await self._load_metadata()
        logger.info("ArtifactManager initialization complete")
    
    async def store_artifact(
        self,
        artifact: Artifact,
        force: bool = False
    ) -> Artifact:
        """Store a new artifact or version.
        
        Args:
            artifact: Artifact to store
            force: Force storage even if version exists
            
        Returns:
            Stored artifact with updated metadata
            
        Raises:
            VersionConflictError: If version already exists and force=False
            StorageError: If storage operation fails
        """
        async with self._lock:
            return await self._store_artifact_internal(artifact, force)
    
    async def _store_artifact_internal(
        self,
        artifact: Artifact,
        force: bool = False
    ) -> Artifact:
        """Internal method to store artifact without acquiring lock."""
        # Check for version conflicts
        if not force and await self._version_exists(artifact.id, artifact.version):
            existing = await self._get_artifact_internal(artifact.id)
            raise VersionConflictError(
                artifact.id,
                artifact.version,
                existing.version
            )
        
        # Calculate checksum
        artifact.checksum = self._calculate_checksum(artifact.content)
        artifact.size_bytes = len(artifact.content.encode('utf-8'))
        
        # Store in filesystem
        try:
            await self._filesystem_storage.store(artifact)
        except Exception as e:
            logger.error(
                "Failed to store artifact",
                artifact_id=str(artifact.id),
                error=str(e)
            )
            raise StorageError(f"Failed to store artifact: {e}")
        
        # Update memory cache
        await self._memory_storage.store(artifact)
        
        # Update indexes
        self._update_indexes(artifact)
        
        # Update metrics
        self._metrics["total_artifacts"] += 1
        self._metrics["storage_operations"] += 1
        
        logger.info(
            "Artifact stored",
            artifact_id=str(artifact.id),
            name=artifact.name,
            version=artifact.version,
            type=artifact.type.value
        )
        
        return artifact
    
    async def get_artifact(
        self,
        artifact_id: UUID,
        version: Optional[int] = None
    ) -> Artifact:
        """Retrieve an artifact by ID and optional version.
        
        Args:
            artifact_id: Artifact ID
            version: Specific version (latest if None)
            
        Returns:
            Retrieved artifact
            
        Raises:
            ArtifactNotFoundError: If artifact not found
        """
        async with self._lock:
            return await self._get_artifact_internal(artifact_id, version)
    
    async def _get_artifact_internal(
        self,
        artifact_id: UUID,
        version: Optional[int] = None
    ) -> Artifact:
        """Internal method to get artifact without lock."""
        # Check memory cache first
        cached = await self._memory_storage.get(artifact_id, version)
        if cached:
            self._metrics["cache_hits"] += 1
            return cached
        
        self._metrics["cache_misses"] += 1
        
        # Load from filesystem
        try:
            artifact = await self._filesystem_storage.get(artifact_id, version)
            if not artifact:
                raise ArtifactNotFoundError(artifact_id)
            
            # Verify integrity
            if not await self._verify_integrity(artifact):
                raise CorruptionError(
                    f"Artifact {artifact_id} failed integrity check",
                    error_code="ARTIFACT_CORRUPTED",
                    details={"artifact_id": str(artifact_id)}
                )
            
            # Update cache
            await self._memory_storage.store(artifact)
            
            return artifact
            
        except Exception as e:
            if isinstance(e, (ArtifactNotFoundError, CorruptionError)):
                raise
            logger.error(
                "Failed to retrieve artifact",
                artifact_id=str(artifact_id),
                version=version,
                error=str(e)
            )
            raise StorageError(f"Failed to retrieve artifact: {e}")
    
    async def update_artifact(
        self,
        artifact_id: UUID,
        new_content: str,
        metadata: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None
    ) -> Artifact:
        """Update an artifact by creating a new version.
        
        Args:
            artifact_id: ID of artifact to update
            new_content: New content
            metadata: Additional metadata to merge
            reason: Reason for update
            
        Returns:
            New version of the artifact
            
        Raises:
            ArtifactNotFoundError: If original artifact not found
        """
        async with self._lock:
            # Get current version
            current = await self._get_artifact_internal(artifact_id)
            
            # Create new version
            new_artifact = current.increment_version()
            new_artifact.content = new_content
            new_artifact.modified_at = datetime.now(timezone.utc)
            
            # Update metadata
            if metadata:
                new_artifact.metadata.update(metadata)
            if reason:
                new_artifact.metadata["update_reason"] = reason
            
            # Store new version using internal method to avoid deadlock
            stored = await self._store_artifact_internal(new_artifact)
            
            # Update version chain
            self._version_chains[artifact_id].append(stored.id)
            
            logger.info(
                "Artifact updated",
                artifact_id=str(artifact_id),
                old_version=current.version,
                new_version=stored.version,
                reason=reason
            )
            
            return stored
    
    async def get_artifact_versions(
        self,
        artifact_id: UUID
    ) -> List[Artifact]:
        """Get all versions of an artifact.
        
        Args:
            artifact_id: Original artifact ID
            
        Returns:
            List of all versions, oldest first
        """
        async with self._lock:
            versions = []
            
            # Get version chain - use set to avoid duplicates
            version_ids = [artifact_id] + self._version_chains.get(artifact_id, [])
            seen_ids = set()
            
            for vid in version_ids:
                if vid in seen_ids:
                    continue
                seen_ids.add(vid)
                try:
                    artifact = await self._get_artifact_internal(vid)
                    versions.append(artifact)
                except ArtifactNotFoundError:
                    logger.warning(
                        "Version missing in chain",
                        artifact_id=str(artifact_id),
                        version_id=str(vid)
                    )
            
            return sorted(versions, key=lambda a: a.version)
    
    async def get_artifacts_by_task(
        self,
        task_id: UUID
    ) -> List[Artifact]:
        """Get all artifacts produced for a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            List of artifacts for the task
        """
        async with self._lock:
            artifact_ids = self._artifacts_by_task.get(task_id, [])
            artifacts = []
            
            for aid in artifact_ids:
                try:
                    artifact = await self._get_artifact_internal(aid)
                    artifacts.append(artifact)
                except ArtifactNotFoundError:
                    logger.warning(
                        "Artifact missing for task",
                        task_id=str(task_id),
                        artifact_id=str(aid)
                    )
            
            return artifacts
    
    async def get_artifacts_by_agent(
        self,
        agent_id: UUID
    ) -> List[Artifact]:
        """Get all artifacts produced by an agent.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            List of artifacts from the agent
        """
        async with self._lock:
            artifact_ids = self._artifacts_by_agent.get(agent_id, [])
            artifacts = []
            
            for aid in artifact_ids:
                try:
                    artifact = await self._get_artifact_internal(aid)
                    artifacts.append(artifact)
                except ArtifactNotFoundError:
                    logger.warning(
                        "Artifact missing for agent",
                        agent_id=str(agent_id),
                        artifact_id=str(aid)
                    )
            
            return artifacts
    
    async def search_artifacts(
        self,
        name_pattern: Optional[str] = None,
        artifact_type: Optional[ArtifactType] = None,
        tags: Optional[Set[str]] = None,
        language: Optional[str] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None
    ) -> List[Artifact]:
        """Search for artifacts matching criteria.
        
        Args:
            name_pattern: Pattern to match artifact names
            artifact_type: Type of artifact
            tags: Tags that must be present
            language: Programming language
            created_after: Created after this time
            created_before: Created before this time
            
        Returns:
            List of matching artifacts
        """
        async with self._lock:
            results = []
            
            # Get all artifact IDs to search
            all_ids = set(self._artifacts_by_id.keys())
            
            for artifact_id in all_ids:
                try:
                    artifact = await self._get_artifact_internal(artifact_id)
                    
                    # Apply filters
                    if name_pattern and name_pattern not in artifact.name:
                        continue
                    if artifact_type and artifact.type != artifact_type:
                        continue
                    if tags and not tags.issubset(artifact.tags):
                        continue
                    if language and artifact.language != language:
                        continue
                    if created_after and artifact.created_at < created_after:
                        continue
                    if created_before and artifact.created_at > created_before:
                        continue
                    
                    results.append(artifact)
                    
                except ArtifactNotFoundError:
                    continue
            
            return results
    
    async def delete_artifact(
        self,
        artifact_id: UUID,
        delete_all_versions: bool = False
    ) -> None:
        """Delete an artifact and optionally all its versions.
        
        Args:
            artifact_id: Artifact to delete
            delete_all_versions: Whether to delete all versions
        """
        async with self._lock:
            # Get artifact to verify it exists
            artifact = await self._get_artifact_internal(artifact_id)
            
            # Determine what to delete
            ids_to_delete = [artifact_id]
            if delete_all_versions:
                ids_to_delete.extend(self._version_chains.get(artifact_id, []))
            
            # Delete from storage
            for aid in ids_to_delete:
                try:
                    await self._filesystem_storage.delete(aid)
                    await self._memory_storage.delete(aid)
                    self._remove_from_indexes(aid)
                except Exception as e:
                    logger.error(
                        "Failed to delete artifact",
                        artifact_id=str(aid),
                        error=str(e)
                    )
            
            logger.info(
                "Artifact deleted",
                artifact_id=str(artifact_id),
                versions_deleted=len(ids_to_delete)
            )
    
    async def cleanup_old_versions(
        self,
        days: Optional[int] = None,
        keep_latest: int = 3
    ) -> int:
        """Clean up old artifact versions.
        
        Args:
            days: Days to keep (uses auto_cleanup_days if None)
            keep_latest: Number of latest versions to keep per artifact
            
        Returns:
            Number of artifacts cleaned up
        """
        days = days or self.auto_cleanup_days
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        cleaned = 0
        
        async with self._lock:
            # Group artifacts by original ID
            version_groups = defaultdict(list)
            for artifact_id in list(self._artifacts_by_id.keys()):
                try:
                    artifact = await self._get_artifact_internal(artifact_id)
                    original_id = artifact.previous_version_id or artifact.id
                    version_groups[original_id].append(artifact)
                except ArtifactNotFoundError:
                    continue
            
            # Clean up old versions
            for original_id, versions in version_groups.items():
                # Sort by version
                versions.sort(key=lambda a: a.version, reverse=True)
                
                # Keep latest versions
                to_delete = versions[keep_latest:]
                
                # Only delete if older than cutoff
                for artifact in to_delete:
                    if artifact.created_at < cutoff_date:
                        await self.delete_artifact(artifact.id)
                        cleaned += 1
        
        logger.info(
            "Cleanup completed",
            artifacts_cleaned=cleaned,
            cutoff_days=days,
            kept_latest=keep_latest
        )
        
        return cleaned
    
    async def export_artifact(
        self,
        artifact_id: UUID,
        export_path: Path,
        include_metadata: bool = True
    ) -> Path:
        """Export an artifact to a file.
        
        Args:
            artifact_id: Artifact to export
            export_path: Path to export to
            include_metadata: Whether to include metadata
            
        Returns:
            Path to exported file
        """
        artifact = await self.get_artifact(artifact_id)
        
        # Ensure export directory exists
        export_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write content
        export_path.write_text(artifact.content, encoding=artifact.encoding)
        
        # Write metadata if requested
        if include_metadata:
            metadata_path = export_path.with_suffix('.meta.json')
            metadata = {
                "id": str(artifact.id),
                "name": artifact.name,
                "type": artifact.type.value,
                "version": artifact.version,
                "language": artifact.language,
                "created_at": artifact.created_at.isoformat(),
                "modified_at": artifact.modified_at.isoformat(),
                "task_id": str(artifact.task_id),
                "agent_id": str(artifact.agent_id),
                "checksum": artifact.checksum,
                "dependencies": [str(d) for d in artifact.dependencies],
                "tags": list(artifact.tags),
                "metadata": artifact.metadata
            }
            metadata_path.write_text(json.dumps(metadata, indent=2))
        
        logger.info(
            "Artifact exported",
            artifact_id=str(artifact_id),
            export_path=str(export_path)
        )
        
        return export_path
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get artifact manager metrics.
        
        Returns:
            Dictionary of metrics
        """
        async with self._lock:
            return {
                **self._metrics,
                "unique_artifacts": len(set(self._artifacts_by_id.keys())),
                "total_tasks": len(self._artifacts_by_task),
                "total_agents": len(self._artifacts_by_agent),
                "cache_size": await self._memory_storage.size(),
                "cache_hit_rate": (
                    self._metrics["cache_hits"] / 
                    max(1, self._metrics["cache_hits"] + self._metrics["cache_misses"])
                )
            }
    
    def _calculate_checksum(self, content: str) -> str:
        """Calculate SHA-256 checksum of content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    async def _verify_integrity(self, artifact: Artifact) -> bool:
        """Verify artifact integrity using checksum."""
        if not artifact.checksum:
            return True  # No checksum to verify
        
        calculated = self._calculate_checksum(artifact.content)
        return calculated == artifact.checksum
    
    async def _version_exists(self, artifact_id: UUID, version: int) -> bool:
        """Check if a specific version exists."""
        try:
            existing = await self._filesystem_storage.get(artifact_id, version)
            return existing is not None
        except:
            return False
    
    def _update_indexes(self, artifact: Artifact) -> None:
        """Update internal indexes when artifact is stored."""
        self._artifacts_by_id[artifact.id] = artifact
        self._artifacts_by_name[artifact.name].append(artifact.id)
        self._artifacts_by_task[artifact.task_id].append(artifact.id)
        self._artifacts_by_agent[artifact.agent_id].append(artifact.id)
        
        if artifact.previous_version_id:
            self._version_chains[artifact.previous_version_id].append(artifact.id)
    
    def _remove_from_indexes(self, artifact_id: UUID) -> None:
        """Remove artifact from internal indexes."""
        if artifact_id not in self._artifacts_by_id:
            return
        
        artifact = self._artifacts_by_id[artifact_id]
        
        # Remove from indexes
        del self._artifacts_by_id[artifact_id]
        
        if artifact.name in self._artifacts_by_name:
            self._artifacts_by_name[artifact.name].remove(artifact_id)
            if not self._artifacts_by_name[artifact.name]:
                del self._artifacts_by_name[artifact.name]
        
        if artifact.task_id in self._artifacts_by_task:
            self._artifacts_by_task[artifact.task_id].remove(artifact_id)
            if not self._artifacts_by_task[artifact.task_id]:
                del self._artifacts_by_task[artifact.task_id]
        
        if artifact.agent_id in self._artifacts_by_agent:
            self._artifacts_by_agent[artifact.agent_id].remove(artifact_id)
            if not self._artifacts_by_agent[artifact.agent_id]:
                del self._artifacts_by_agent[artifact.agent_id]
    
    async def _load_metadata(self) -> None:
        """Load artifact metadata from storage on startup."""
        try:
            metadata = await self._filesystem_storage.load_metadata()
            
            for artifact_meta in metadata:
                artifact_id = UUID(artifact_meta["id"])
                self._artifacts_by_id[artifact_id] = None  # Placeholder
                self._artifacts_by_name[artifact_meta["name"]].append(artifact_id)
                self._artifacts_by_task[UUID(artifact_meta["task_id"])].append(artifact_id)
                self._artifacts_by_agent[UUID(artifact_meta["agent_id"])].append(artifact_id)
                
                if "previous_version_id" in artifact_meta and artifact_meta["previous_version_id"]:
                    prev_id = UUID(artifact_meta["previous_version_id"])
                    self._version_chains[prev_id].append(artifact_id)
            
            self._metrics["total_artifacts"] = len(self._artifacts_by_id)
            
            logger.info(
                "Metadata loaded",
                artifacts_count=len(self._artifacts_by_id)
            )
            
        except Exception as e:
            logger.error(
                "Failed to load metadata",
                error=str(e)
            )
            # Continue with empty metadata - system will rebuild as artifacts are accessed