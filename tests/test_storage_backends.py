"""Tests for storage backend implementations."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from src.core.interfaces import Artifact, ArtifactType
from src.storage.filesystem_storage import FilesystemStorage
from src.storage.memory_storage import MemoryStorage


@pytest.fixture
def sample_artifact():
    """Create a sample artifact for testing."""
    return Artifact(
        id=uuid4(),
        name="test.py",
        type=ArtifactType.SOURCE_CODE,
        content="print('hello world')",
        path=Path("test.py"),
        language="python",
        version=1,
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc),
        task_id=uuid4(),
        agent_id=uuid4()
    )


class TestMemoryStorage:
    """Test cases for MemoryStorage."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, sample_artifact):
        """Test basic store and retrieve operations."""
        storage = MemoryStorage(max_size=10)

        # Store artifact
        await storage.store(sample_artifact)

        # Retrieve artifact
        retrieved = await storage.get(sample_artifact.id)
        assert retrieved is not None
        assert retrieved.id == sample_artifact.id
        assert retrieved.content == sample_artifact.content

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        storage = MemoryStorage(max_size=3)

        # Create and store artifacts
        artifacts = []
        for i in range(4):
            artifact = Artifact(
                id=uuid4(),
                name=f"test{i}.py",
                type=ArtifactType.SOURCE_CODE,
                content=f"# Test {i}",
                path=Path(f"test{i}.py"),
                version=1,
                created_at=datetime.now(timezone.utc),
                modified_at=datetime.now(timezone.utc),
                task_id=uuid4(),
                agent_id=uuid4()
            )
            artifacts.append(artifact)
            await storage.store(artifact)

        # First artifact should be evicted
        assert await storage.get(artifacts[0].id) is None

        # Others should still be in cache
        for i in range(1, 4):
            assert await storage.get(artifacts[i].id) is not None

    @pytest.mark.asyncio
    async def test_cache_stats(self, sample_artifact):
        """Test cache statistics tracking."""
        storage = MemoryStorage(max_size=10)

        # Initial stats
        stats = await storage.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0

        # Store and retrieve
        await storage.store(sample_artifact)
        await storage.get(sample_artifact.id)  # Hit
        await storage.get(uuid4())  # Miss

        stats = await storage.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] > 0


class TestFilesystemStorage:
    """Test cases for FilesystemStorage."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, tmp_path, sample_artifact):
        """Test basic store and retrieve operations."""
        storage = FilesystemStorage(
            base_path=tmp_path,
            enable_compression=False
        )
        await storage.initialize()

        # Store artifact
        await storage.store(sample_artifact)

        # Retrieve artifact
        retrieved = await storage.get(sample_artifact.id)
        assert retrieved is not None
        assert retrieved.id == sample_artifact.id
        assert retrieved.content == sample_artifact.content

    @pytest.mark.asyncio
    async def test_compression(self, tmp_path, sample_artifact):
        """Test artifact compression."""
        # Create large content
        sample_artifact.content = "x" * 10000

        # Store without compression
        storage_uncompressed = FilesystemStorage(
            base_path=tmp_path / "uncompressed",
            enable_compression=False
        )
        await storage_uncompressed.initialize()
        await storage_uncompressed.store(sample_artifact)

        # Store with compression
        storage_compressed = FilesystemStorage(
            base_path=tmp_path / "compressed",
            enable_compression=True
        )
        await storage_compressed.initialize()
        await storage_compressed.store(sample_artifact)

        # Compare file sizes
        uncompressed_path = storage_uncompressed._get_artifact_path(
            sample_artifact.id, sample_artifact.version
        )
        compressed_path = storage_compressed._get_artifact_path(
            sample_artifact.id, sample_artifact.version
        )

        assert compressed_path.stat().st_size < uncompressed_path.stat().st_size

        # Verify content is preserved
        retrieved = await storage_compressed.get(sample_artifact.id)
        assert retrieved.content == sample_artifact.content

    @pytest.mark.asyncio
    async def test_metadata_persistence(self, tmp_path):
        """Test metadata loading and persistence."""
        storage = FilesystemStorage(base_path=tmp_path)
        await storage.initialize()

        # Store multiple artifacts
        artifacts = []
        for i in range(3):
            artifact = Artifact(
                id=uuid4(),
                name=f"test{i}.py",
                type=ArtifactType.SOURCE_CODE,
                content=f"# Test {i}",
                path=Path(f"test{i}.py"),
                version=1,
                created_at=datetime.now(timezone.utc),
                modified_at=datetime.now(timezone.utc),
                task_id=uuid4(),
                agent_id=uuid4()
            )
            artifacts.append(artifact)
            await storage.store(artifact)

        # Load metadata
        metadata = await storage.load_metadata()
        assert len(metadata) == 3

        # Verify metadata content
        stored_ids = {m["id"] for m in metadata}
        expected_ids = {str(a.id) for a in artifacts}
        assert stored_ids == expected_ids
