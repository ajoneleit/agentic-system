"""In-memory storage backend for artifacts with LRU cache.

This module provides fast in-memory caching of artifacts with
size-based eviction and thread-safe operations.
"""

import asyncio
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from structlog import get_logger

from src.core.interfaces import Artifact

logger = get_logger(__name__)


class MemoryStorage:
    """In-memory LRU cache for artifacts."""
    
    def __init__(self, max_size: int = 100):
        """Initialize memory storage.
        
        Args:
            max_size: Maximum number of artifacts to cache
        """
        self.max_size = max_size
        self._cache: OrderedDict[Tuple[UUID, int], Artifact] = OrderedDict()
        self._lock = asyncio.Lock()
        
        # Cache statistics
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "stores": 0
        }
        
        logger.info(
            "MemoryStorage initialized",
            max_size=max_size
        )
    
    async def store(self, artifact: Artifact) -> None:
        """Store an artifact in memory.
        
        Args:
            artifact: Artifact to store
        """
        async with self._lock:
            key = (artifact.id, artifact.version)
            
            # If already exists, move to end (most recently used)
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                # Add new entry
                self._cache[key] = artifact
                self._stats["stores"] += 1
                
                # Evict oldest if over capacity
                if len(self._cache) > self.max_size:
                    evicted_key = next(iter(self._cache))
                    del self._cache[evicted_key]
                    self._stats["evictions"] += 1
                    
                    logger.debug(
                        "Artifact evicted from cache",
                        artifact_id=str(evicted_key[0]),
                        version=evicted_key[1]
                    )
            
            logger.debug(
                "Artifact cached",
                artifact_id=str(artifact.id),
                version=artifact.version,
                cache_size=len(self._cache)
            )
    
    async def get(
        self,
        artifact_id: UUID,
        version: Optional[int] = None
    ) -> Optional[Artifact]:
        """Retrieve an artifact from memory.
        
        Args:
            artifact_id: Artifact ID
            version: Specific version (latest if None)
            
        Returns:
            Cached artifact or None if not found
        """
        async with self._lock:
            if version is None:
                # Find latest version
                latest_artifact = None
                latest_version = -1
                
                for (aid, ver), artifact in self._cache.items():
                    if aid == artifact_id and ver > latest_version:
                        latest_version = ver
                        latest_artifact = artifact
                
                if latest_artifact:
                    # Move to end (most recently used)
                    self._cache.move_to_end((artifact_id, latest_version))
                    self._stats["hits"] += 1
                    
                    logger.debug(
                        "Cache hit (latest version)",
                        artifact_id=str(artifact_id),
                        version=latest_version
                    )
                else:
                    self._stats["misses"] += 1
                
                return latest_artifact
            else:
                # Get specific version
                key = (artifact_id, version)
                
                if key in self._cache:
                    # Move to end (most recently used)
                    self._cache.move_to_end(key)
                    self._stats["hits"] += 1
                    
                    logger.debug(
                        "Cache hit",
                        artifact_id=str(artifact_id),
                        version=version
                    )
                    
                    return self._cache[key]
                else:
                    self._stats["misses"] += 1
                    return None
    
    async def delete(
        self,
        artifact_id: UUID,
        version: Optional[int] = None
    ) -> None:
        """Remove an artifact from memory.
        
        Args:
            artifact_id: Artifact ID
            version: Specific version (all versions if None)
        """
        async with self._lock:
            if version is None:
                # Delete all versions
                keys_to_delete = [
                    key for key in self._cache
                    if key[0] == artifact_id
                ]
                
                for key in keys_to_delete:
                    del self._cache[key]
                
                logger.debug(
                    "All versions removed from cache",
                    artifact_id=str(artifact_id),
                    versions_removed=len(keys_to_delete)
                )
            else:
                # Delete specific version
                key = (artifact_id, version)
                if key in self._cache:
                    del self._cache[key]
                    
                    logger.debug(
                        "Artifact removed from cache",
                        artifact_id=str(artifact_id),
                        version=version
                    )
    
    async def clear(self) -> None:
        """Clear all cached artifacts."""
        async with self._lock:
            size_before = len(self._cache)
            self._cache.clear()
            
            logger.info(
                "Cache cleared",
                artifacts_removed=size_before
            )
    
    async def size(self) -> int:
        """Get number of cached artifacts.
        
        Returns:
            Current cache size
        """
        async with self._lock:
            return len(self._cache)
    
    async def get_stats(self) -> Dict[str, int]:
        """Get cache statistics.
        
        Returns:
            Dictionary of cache statistics
        """
        async with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (
                self._stats["hits"] / total_requests
                if total_requests > 0
                else 0.0
            )
            
            return {
                **self._stats,
                "size": len(self._cache),
                "max_size": self.max_size,
                "hit_rate": round(hit_rate, 3)
            }
    
    async def get_memory_usage(self) -> Dict[str, int]:
        """Estimate memory usage of cached artifacts.
        
        Returns:
            Memory usage statistics in bytes
        """
        async with self._lock:
            total_content_size = 0
            total_metadata_size = 0
            
            for artifact in self._cache.values():
                # Content size
                total_content_size += len(artifact.content.encode('utf-8'))
                
                # Rough estimate of metadata size
                total_metadata_size += (
                    # UUIDs: ~36 bytes each
                    36 * 5 +  # id, task_id, agent_id, prev_version_id
                    # Strings
                    len(artifact.name.encode('utf-8')) +
                    len(artifact.language.encode('utf-8')) if artifact.language else 0 +
                    # Other fields
                    100  # Rough estimate for other fields
                )
            
            return {
                "total_bytes": total_content_size + total_metadata_size,
                "content_bytes": total_content_size,
                "metadata_bytes": total_metadata_size,
                "average_artifact_bytes": (
                    (total_content_size + total_metadata_size) // len(self._cache)
                    if self._cache else 0
                )
            }
    
    async def warmup(self, artifacts: List[Artifact]) -> None:
        """Pre-populate cache with frequently used artifacts.
        
        Args:
            artifacts: List of artifacts to cache
        """
        async with self._lock:
            # Clear existing cache
            self._cache.clear()
            
            # Add artifacts (up to max_size)
            for artifact in artifacts[:self.max_size]:
                key = (artifact.id, artifact.version)
                self._cache[key] = artifact
            
            logger.info(
                "Cache warmed up",
                artifacts_loaded=len(self._cache)
            )
    
    async def get_lru_info(self) -> List[Dict[str, Any]]:
        """Get information about cache entries in LRU order.
        
        Returns:
            List of cache entry info, oldest first
        """
        async with self._lock:
            entries = []
            
            for (artifact_id, version), artifact in self._cache.items():
                entries.append({
                    "artifact_id": str(artifact_id),
                    "version": version,
                    "name": artifact.name,
                    "type": artifact.type.value,
                    "size_bytes": artifact.size_bytes,
                    "created_at": artifact.created_at.isoformat(),
                    "modified_at": artifact.modified_at.isoformat()
                })
            
            return entries
    
    async def has_artifact(
        self,
        artifact_id: UUID,
        version: Optional[int] = None
    ) -> bool:
        """Check if an artifact is in cache.
        
        Args:
            artifact_id: Artifact ID
            version: Specific version (any version if None)
            
        Returns:
            True if artifact is cached
        """
        async with self._lock:
            if version is None:
                # Check if any version exists
                return any(
                    aid == artifact_id
                    for aid, _ in self._cache.keys()
                )
            else:
                # Check specific version
                return (artifact_id, version) in self._cache
    
    async def touch(self, artifact_id: UUID, version: int) -> bool:
        """Update access time for an artifact without retrieving it.
        
        Args:
            artifact_id: Artifact ID
            version: Version number
            
        Returns:
            True if artifact was found and touched
        """
        async with self._lock:
            key = (artifact_id, version)
            
            if key in self._cache:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                return True
            
            return False