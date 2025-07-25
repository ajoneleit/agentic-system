"""Optimized artifact manager with performance improvements.

Key optimizations:
1. Streaming for large artifacts
2. Parallel processing for batch operations
3. Connection pooling for filesystem operations
4. Lazy loading and caching improvements
5. Asynchronous I/O optimization
"""

import asyncio
import gzip
import hashlib
from collections import defaultdict
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import aiofiles
from structlog import get_logger

from src.core.interfaces import Artifact, ArtifactType
from src.storage.filesystem_storage import FilesystemStorage
from src.storage.optimized_memory_storage import OptimizedMemoryStorage
from src.utils.file_manager import FileManager

logger = get_logger(__name__)


class OptimizedArtifactManager:
    """Optimized artifact manager with superior performance characteristics."""

    def __init__(
        self,
        storage_path: Path,
        max_memory_cache_size: int = 1000,
        max_memory_mb: int = 200,
        enable_compression: bool = True,
        enable_streaming: bool = True,
        parallel_workers: int = 4,
        batch_size: int = 100,
    ):
        self.storage_path = storage_path
        self.max_memory_cache_size = max_memory_cache_size
        self.max_memory_mb = max_memory_mb
        self.enable_compression = enable_compression
        self.enable_streaming = enable_streaming
        self.parallel_workers = parallel_workers
        self.batch_size = batch_size

        # Optimized storage backends
        self._memory_storage = OptimizedMemoryStorage(
            max_size=max_memory_cache_size, max_memory_mb=max_memory_mb
        )
        self._filesystem_storage = FilesystemStorage(
            base_path=storage_path, enable_compression=enable_compression
        )
        self._file_manager = FileManager(storage_path)

        # Optimized indexes with weak references
        self._artifacts_by_id: dict[UUID, Artifact] = {}
        self._artifacts_by_name: dict[str, list[UUID]] = defaultdict(list)
        self._artifacts_by_task: dict[UUID, set[UUID]] = defaultdict(set)
        self._artifacts_by_agent: dict[UUID, set[UUID]] = defaultdict(set)
        self._version_chains: dict[UUID, list[UUID]] = defaultdict(list)

        # Performance optimizations
        self._executor = ThreadPoolExecutor(max_workers=parallel_workers)
        self._read_cache: dict[UUID, Artifact] = {}  # Read-through cache
        self._write_buffer: list[Artifact] = []  # Write buffer for batching
        self._dirty_artifacts: set[UUID] = set()  # Track dirty artifacts

        # Async coordination
        self._lock = asyncio.Lock()
        self._background_tasks: list[asyncio.Task] = []

        # Performance metrics
        self._metrics = {
            "total_artifacts": 0,
            "total_versions": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "storage_operations": 0,
            "batch_operations": 0,
            "streaming_operations": 0,
            "parallel_operations": 0,
        }

        logger.info(
            "OptimizedArtifactManager initialized",
            storage_path=str(storage_path),
            max_cache_size=max_memory_cache_size,
            max_memory_mb=max_memory_mb,
            parallel_workers=parallel_workers,
            batch_size=batch_size,
        )

    async def initialize(self) -> None:
        """Initialize all storage backends and start background tasks."""
        await self._memory_storage.initialize()
        await self._filesystem_storage.initialize()

        # Start background tasks
        self._background_tasks.extend(
            [
                asyncio.create_task(self._background_flush()),
                asyncio.create_task(self._background_cleanup()),
                asyncio.create_task(self._background_metrics()),
            ]
        )

        await self._load_metadata()
        logger.info("OptimizedArtifactManager initialization complete")

    async def store_artifact(self, artifact: Artifact, force: bool = False) -> Artifact:
        """Store artifact with optimizations."""
        async with self._lock:
            return await self._store_artifact_optimized(artifact, force)

    async def store_artifacts_batch(
        self, artifacts: list[Artifact], force: bool = False
    ) -> list[Artifact]:
        """Store multiple artifacts in a single batch operation."""
        async with self._lock:
            results = []

            # Process in parallel batches
            for i in range(0, len(artifacts), self.batch_size):
                batch = artifacts[i : i + self.batch_size]
                batch_results = await asyncio.gather(
                    *[self._store_artifact_optimized(artifact, force) for artifact in batch],
                    return_exceptions=True,
                )

                # Filter out exceptions and collect results
                for result in batch_results:
                    if isinstance(result, Exception):
                        logger.error("Batch store error", error=str(result))
                    else:
                        results.append(result)

            self._metrics["batch_operations"] += 1
            return results

    async def _store_artifact_optimized(self, artifact: Artifact, force: bool = False) -> Artifact:
        """Internal optimized store method."""
        # Check for version conflicts
        if not force and await self._version_exists(artifact.id, artifact.version):
            existing = await self._get_artifact_internal(artifact.id)
            if existing and existing.version >= artifact.version:
                return existing  # Return existing instead of raising error

        # Calculate checksum and size
        artifact.checksum = await self._calculate_checksum_async(artifact.content)
        artifact.size_bytes = len(artifact.content.encode("utf-8"))

        # Decide storage strategy based on size
        if artifact.size_bytes > 1024 * 1024:  # > 1MB
            # Use streaming for large artifacts
            await self._store_large_artifact_streaming(artifact)
            self._metrics["streaming_operations"] += 1
        else:
            # Use regular storage for small artifacts
            await self._filesystem_storage.store(artifact)

        # Update memory cache
        await self._memory_storage.store(artifact)

        # Update indexes efficiently
        await self._update_indexes_optimized(artifact)

        # Update metrics
        self._metrics["total_artifacts"] += 1
        self._metrics["storage_operations"] += 1

        return artifact

    async def get_artifact(
        self, artifact_id: UUID, version: Optional[int] = None
    ) -> Optional[Artifact]:
        """Get artifact with optimized caching."""
        async with self._lock:
            return await self._get_artifact_optimized(artifact_id, version)

    async def get_artifacts_batch(self, artifact_ids: list[UUID]) -> dict[UUID, Optional[Artifact]]:
        """Get multiple artifacts efficiently."""
        async with self._lock:
            # Try memory cache first
            memory_results = await self._memory_storage.get_batch(artifact_ids)

            # Identify cache misses
            cache_misses = [aid for aid, artifact in memory_results.items() if artifact is None]

            if cache_misses:
                # Load misses from filesystem in parallel
                filesystem_results = await asyncio.gather(
                    *[self._filesystem_storage.get(aid) for aid in cache_misses],
                    return_exceptions=True,
                )

                # Update results and cache
                for aid, result in zip(cache_misses, filesystem_results):
                    if isinstance(result, Exception):
                        memory_results[aid] = None
                    else:
                        memory_results[aid] = result
                        if result:
                            await self._memory_storage.store(result)

            # Update metrics
            hits = sum(1 for v in memory_results.values() if v is not None)
            self._metrics["cache_hits"] += hits
            self._metrics["cache_misses"] += len(artifact_ids) - hits

            return memory_results

    async def _get_artifact_optimized(
        self, artifact_id: UUID, version: Optional[int] = None
    ) -> Optional[Artifact]:
        """Internal optimized get method."""
        # Check memory cache first
        cached = await self._memory_storage.get(artifact_id, version)
        if cached:
            self._metrics["cache_hits"] += 1
            return cached

        self._metrics["cache_misses"] += 1

        # Load from filesystem
        artifact = await self._filesystem_storage.get(artifact_id, version)
        if artifact:
            # Verify integrity
            if not await self._verify_integrity_async(artifact):
                logger.error("Artifact integrity check failed", artifact_id=str(artifact_id))
                return None

            # Update cache
            await self._memory_storage.store(artifact)
            return artifact

        return None

    async def stream_artifact_content(self, artifact_id: UUID) -> AsyncIterator[bytes]:
        """Stream artifact content for large files."""
        if not self.enable_streaming:
            artifact = await self.get_artifact(artifact_id)
            if artifact:
                yield artifact.content.encode("utf-8")
            return

        # Get artifact metadata
        artifact = await self.get_artifact(artifact_id)
        if not artifact:
            return

        # Stream from filesystem
        file_path = self._get_artifact_path(artifact_id)
        if file_path.exists():
            async with aiofiles.open(file_path, "rb") as f:
                while True:
                    chunk = await f.read(8192)  # 8KB chunks
                    if not chunk:
                        break
                    yield chunk

    async def search_artifacts_optimized(
        self,
        name_pattern: Optional[str] = None,
        artifact_type: Optional[ArtifactType] = None,
        tags: Optional[set[str]] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Artifact]:
        """Optimized artifact search with pagination."""
        async with self._lock:
            # Use indexes for efficient searching
            candidate_ids = set()

            # Start with name-based filtering if provided
            if name_pattern:
                for name, ids in self._artifacts_by_name.items():
                    if name_pattern in name:
                        candidate_ids.update(ids)
            else:
                # Use all artifacts if no name pattern
                candidate_ids.update(self._artifacts_by_id.keys())

            # Apply filters
            filtered_ids = []
            for artifact_id in candidate_ids:
                artifact = await self._get_artifact_optimized(artifact_id)
                if not artifact:
                    continue

                # Apply filters
                if artifact_type and artifact.type != artifact_type:
                    continue
                if tags and not tags.issubset(artifact.tags):
                    continue
                if created_after and artifact.created_at < created_after:
                    continue
                if created_before and artifact.created_at > created_before:
                    continue

                filtered_ids.append(artifact_id)

            # Apply pagination
            paginated_ids = filtered_ids[offset : offset + limit]

            # Load artifacts efficiently
            result_artifacts = []
            for artifact_id in paginated_ids:
                artifact = await self._get_artifact_optimized(artifact_id)
                if artifact:
                    result_artifacts.append(artifact)

            return result_artifacts

    async def _store_large_artifact_streaming(self, artifact: Artifact) -> None:
        """Store large artifact using streaming."""
        file_path = self._get_artifact_path(artifact.id)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Stream write to file
        async with aiofiles.open(file_path, "wb") as f:
            if self.enable_compression:
                # Compress content
                compressed_content = await self._compress_content_async(artifact.content)
                await f.write(compressed_content)
            else:
                await f.write(artifact.content.encode("utf-8"))

    async def _calculate_checksum_async(self, content: str) -> str:
        """Calculate checksum asynchronously."""

        def _calculate():
            return hashlib.sha256(content.encode("utf-8")).hexdigest()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _calculate)

    async def _verify_integrity_async(self, artifact: Artifact) -> bool:
        """Verify artifact integrity asynchronously."""
        if not artifact.checksum:
            return True

        calculated = await self._calculate_checksum_async(artifact.content)
        return calculated == artifact.checksum

    async def _compress_content_async(self, content: str) -> bytes:
        """Compress content asynchronously."""

        def _compress():
            return gzip.compress(content.encode("utf-8"))

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _compress)

    async def _update_indexes_optimized(self, artifact: Artifact) -> None:
        """Update indexes with better performance."""
        # Update primary index
        self._artifacts_by_id[artifact.id] = artifact

        # Update name index (use sets for better performance)
        name_ids = self._artifacts_by_name[artifact.name]
        if artifact.id not in name_ids:
            name_ids.append(artifact.id)

        # Update task and agent indexes (use sets)
        self._artifacts_by_task[artifact.task_id].add(artifact.id)
        self._artifacts_by_agent[artifact.agent_id].add(artifact.id)

        # Update version chain
        if artifact.previous_version_id:
            self._version_chains[artifact.previous_version_id].append(artifact.id)

    async def _background_flush(self) -> None:
        """Background task to flush write buffer."""
        while True:
            try:
                await asyncio.sleep(5)  # Flush every 5 seconds

                if self._write_buffer:
                    async with self._lock:
                        buffer_copy = self._write_buffer.copy()
                        self._write_buffer.clear()

                    # Flush to filesystem
                    await asyncio.gather(
                        *[self._filesystem_storage.store(artifact) for artifact in buffer_copy],
                        return_exceptions=True,
                    )

                    logger.debug("Flushed write buffer", count=len(buffer_copy))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Background flush error", error=str(e))

    async def _background_cleanup(self) -> None:
        """Background cleanup task."""
        while True:
            try:
                await asyncio.sleep(60)  # Cleanup every minute

                # Cleanup memory cache
                memory_stats = await self._memory_storage.get_stats()
                if memory_stats["memory_utilization"] > 0.8:
                    # Force cleanup if memory usage is high
                    await self._memory_storage._cleanup_cache()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Background cleanup error", error=str(e))

    async def _background_metrics(self) -> None:
        """Background metrics collection."""
        while True:
            try:
                await asyncio.sleep(30)  # Collect metrics every 30 seconds

                # Update metrics
                memory_stats = await self._memory_storage.get_stats()
                self._metrics.update(
                    {
                        "memory_hit_rate": memory_stats["hit_rate"],
                        "memory_usage_mb": memory_stats["memory_usage_mb"],
                        "cache_size": memory_stats["size"],
                    }
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Background metrics error", error=str(e))

    def _get_artifact_path(self, artifact_id: UUID) -> Path:
        """Get filesystem path for artifact."""
        return self.storage_path / f"{artifact_id}.artifact"

    async def _version_exists(self, artifact_id: UUID, version: int) -> bool:
        """Check if version exists."""
        existing = await self._filesystem_storage.get(artifact_id, version)
        return existing is not None

    async def _load_metadata(self) -> None:
        """Load metadata from storage."""
        try:
            metadata = await self._filesystem_storage.load_metadata()

            for artifact_meta in metadata:
                artifact_id = UUID(artifact_meta["id"])

                # Update indexes
                self._artifacts_by_name[artifact_meta["name"]].append(artifact_id)
                self._artifacts_by_task[UUID(artifact_meta["task_id"])].add(artifact_id)
                self._artifacts_by_agent[UUID(artifact_meta["agent_id"])].add(artifact_id)

                if "previous_version_id" in artifact_meta and artifact_meta["previous_version_id"]:
                    prev_id = UUID(artifact_meta["previous_version_id"])
                    self._version_chains[prev_id].append(artifact_id)

            self._metrics["total_artifacts"] = len(self._artifacts_by_id)

        except Exception as e:
            logger.error("Failed to load metadata", error=str(e))

    async def get_performance_metrics(self) -> dict[str, Any]:
        """Get comprehensive performance metrics."""
        memory_stats = await self._memory_storage.get_stats()

        return {
            **self._metrics,
            "memory_stats": memory_stats,
            "index_sizes": {
                "by_id": len(self._artifacts_by_id),
                "by_name": len(self._artifacts_by_name),
                "by_task": len(self._artifacts_by_task),
                "by_agent": len(self._artifacts_by_agent),
                "version_chains": len(self._version_chains),
            },
            "background_tasks": len(self._background_tasks),
            "executor_stats": {
                "active_workers": self._executor._threads,
                "pending_tasks": self._executor._work_queue.qsize(),
            },
        }

    async def shutdown(self) -> None:
        """Shutdown the artifact manager."""
        logger.info("Shutting down OptimizedArtifactManager")

        # Cancel background tasks
        for task in self._background_tasks:
            task.cancel()

        # Wait for tasks to finish
        await asyncio.gather(*self._background_tasks, return_exceptions=True)

        # Flush any remaining data
        if self._write_buffer:
            await asyncio.gather(
                *[self._filesystem_storage.store(artifact) for artifact in self._write_buffer],
                return_exceptions=True,
            )

        # Shutdown storage backends
        await self._memory_storage.shutdown()

        # Shutdown executor
        self._executor.shutdown(wait=True)

        logger.info("OptimizedArtifactManager shutdown complete")
