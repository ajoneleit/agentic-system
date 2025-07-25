"""Tests for the Artifact Management System."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from src.core.artifact_manager import (
    ArtifactManager,
    ArtifactNotFoundError,
    VersionConflictError,
)
from src.core.interfaces import Artifact, ArtifactType


@pytest.fixture
async def artifact_manager(tmp_path):
    """Create an artifact manager for testing."""
    manager = ArtifactManager(
        storage_path=tmp_path / "artifacts",
        max_memory_cache_size=10,
        enable_compression=True,
        auto_cleanup_days=7
    )
    await manager.initialize()
    yield manager
    # Cleanup is automatic with tmp_path


@pytest.fixture
def sample_artifact():
    """Create a sample artifact for testing."""
    return Artifact(
        id=uuid4(),
        name="test_module.py",
        type=ArtifactType.SOURCE_CODE,
        content='def test_function():\n    return "Hello, Test!"',
        path=Path("src/test_module.py"),
        language="python",
        version=1,
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc),
        task_id=uuid4(),
        agent_id=uuid4(),
        tags={"test", "module"},
        metadata={"author": "test_agent"}
    )


class TestArtifactManager:
    """Test cases for ArtifactManager."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve_artifact(self, artifact_manager, sample_artifact):
        """Test storing and retrieving an artifact."""
        # Store artifact
        stored = await artifact_manager.store_artifact(sample_artifact)
        assert stored.id == sample_artifact.id
        assert stored.checksum is not None
        assert stored.size_bytes > 0

        # Retrieve artifact
        retrieved = await artifact_manager.get_artifact(sample_artifact.id)
        assert retrieved.id == sample_artifact.id
        assert retrieved.content == sample_artifact.content
        assert retrieved.name == sample_artifact.name

    @pytest.mark.asyncio
    async def test_version_management(self, artifact_manager, sample_artifact):
        """Test artifact versioning."""
        # Store initial version
        v1 = await artifact_manager.store_artifact(sample_artifact)
        assert v1.version == 1

        # Update artifact
        new_content = 'def test_function():\n    return "Hello, Updated!"'
        v2 = await artifact_manager.update_artifact(
            sample_artifact.id,
            new_content,
            reason="Updated greeting message"
        )
        assert v2.version == 2
        assert v2.content == new_content
        assert v2.previous_version_id == v1.id

        # Get all versions
        versions = await artifact_manager.get_artifact_versions(sample_artifact.id)
        assert len(versions) == 2
        assert versions[0].version == 1
        assert versions[1].version == 2

        # Get specific version
        v1_retrieved = await artifact_manager.get_artifact(sample_artifact.id, version=1)
        assert v1_retrieved.version == 1
        assert v1_retrieved.content == sample_artifact.content

    @pytest.mark.asyncio
    async def test_artifact_not_found(self, artifact_manager):
        """Test retrieving non-existent artifact."""
        with pytest.raises(ArtifactNotFoundError):
            await artifact_manager.get_artifact(uuid4())

    @pytest.mark.asyncio
    async def test_version_conflict(self, artifact_manager, sample_artifact):
        """Test version conflict detection."""
        # Store initial version
        await artifact_manager.store_artifact(sample_artifact)

        # Try to store same version again without force
        with pytest.raises(VersionConflictError):
            await artifact_manager.store_artifact(sample_artifact)

        # Force store should work
        forced = await artifact_manager.store_artifact(sample_artifact, force=True)
        assert forced.version == 1

    @pytest.mark.asyncio
    async def test_search_artifacts(self, artifact_manager):
        """Test artifact search functionality."""
        # Create and store multiple artifacts
        artifacts = []
        for i in range(3):
            artifact = Artifact(
                id=uuid4(),
                name=f"module_{i}.py",
                type=ArtifactType.SOURCE_CODE,
                content=f"# Module {i}",
                path=Path(f"module_{i}.py"),
                language="python",
                version=1,
                created_at=datetime.now(timezone.utc),
                modified_at=datetime.now(timezone.utc),
                task_id=uuid4(),
                agent_id=uuid4(),
                tags={f"tag{i}", "python"},
                metadata={"index": i}
            )
            stored = await artifact_manager.store_artifact(artifact)
            artifacts.append(stored)

        # Search by language
        results = await artifact_manager.search_artifacts(language="python")
        assert len(results) == 3

        # Search by name pattern
        results = await artifact_manager.search_artifacts(name_pattern="module_1")
        assert len(results) == 1
        assert results[0].name == "module_1.py"

        # Search by tags
        results = await artifact_manager.search_artifacts(tags={"tag1"})
        assert len(results) == 1
        assert "tag1" in results[0].tags

    @pytest.mark.asyncio
    async def test_artifacts_by_task(self, artifact_manager):
        """Test retrieving artifacts by task."""
        task_id = uuid4()

        # Create artifacts for the same task
        artifacts = []
        for i in range(2):
            artifact = Artifact(
                id=uuid4(),
                name=f"task_artifact_{i}.py",
                type=ArtifactType.SOURCE_CODE,
                content=f"# Task artifact {i}",
                path=Path(f"task_artifact_{i}.py"),
                language="python",
                version=1,
                created_at=datetime.now(timezone.utc),
                modified_at=datetime.now(timezone.utc),
                task_id=task_id,
                agent_id=uuid4(),
            )
            stored = await artifact_manager.store_artifact(artifact)
            artifacts.append(stored)

        # Get artifacts by task
        task_artifacts = await artifact_manager.get_artifacts_by_task(task_id)
        assert len(task_artifacts) == 2
        assert all(a.task_id == task_id for a in task_artifacts)

    @pytest.mark.asyncio
    async def test_delete_artifact(self, artifact_manager, sample_artifact):
        """Test artifact deletion."""
        # Store artifact
        await artifact_manager.store_artifact(sample_artifact)

        # Verify it exists
        retrieved = await artifact_manager.get_artifact(sample_artifact.id)
        assert retrieved is not None

        # Delete artifact
        await artifact_manager.delete_artifact(sample_artifact.id)

        # Verify it's gone
        with pytest.raises(ArtifactNotFoundError):
            await artifact_manager.get_artifact(sample_artifact.id)

    @pytest.mark.asyncio
    async def test_cache_performance(self, artifact_manager, sample_artifact):
        """Test cache hit/miss behavior."""
        # Store artifact
        await artifact_manager.store_artifact(sample_artifact)

        # Clear memory cache to force cache miss
        await artifact_manager._memory_storage.clear()

        # First retrieval (cache miss)
        metrics_before = await artifact_manager.get_metrics()
        cache_misses_before = metrics_before["cache_misses"]

        await artifact_manager.get_artifact(sample_artifact.id)

        # Second retrieval (cache hit)
        await artifact_manager.get_artifact(sample_artifact.id)

        metrics_after = await artifact_manager.get_metrics()
        assert metrics_after["cache_hits"] > metrics_before.get("cache_hits", 0)
        assert metrics_after["cache_misses"] == cache_misses_before + 1

    @pytest.mark.asyncio
    async def test_export_artifact(self, artifact_manager, sample_artifact, tmp_path):
        """Test artifact export functionality."""
        # Store artifact
        await artifact_manager.store_artifact(sample_artifact)

        # Export artifact
        export_path = tmp_path / "exported" / "test_module.py"
        exported = await artifact_manager.export_artifact(
            sample_artifact.id,
            export_path,
            include_metadata=True
        )

        # Verify export
        assert exported.exists()
        assert exported.read_text() == sample_artifact.content

        # Verify metadata export
        metadata_path = export_path.with_suffix('.meta.json')
        assert metadata_path.exists()

        import json
        metadata = json.loads(metadata_path.read_text())
        assert metadata["id"] == str(sample_artifact.id)
        assert metadata["name"] == sample_artifact.name
        assert metadata["version"] == sample_artifact.version
