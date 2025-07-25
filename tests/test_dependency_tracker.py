"""Tests for dependency tracking functionality."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from src.core.dependency_tracker import (
    CyclicDependencyError,
    DependencyTracker,
)
from src.core.interfaces import Artifact, ArtifactType


class TestDependencyTracker:
    """Test cases for DependencyTracker."""

    @pytest.fixture
    def tracker(self):
        """Create a dependency tracker instance."""
        return DependencyTracker()

    @pytest.fixture
    def python_artifact(self):
        """Create a Python artifact with imports."""
        return Artifact(
            id=uuid4(),
            name="main.py",
            type=ArtifactType.SOURCE_CODE,
            content="""import os
import json
from pathlib import Path
from utils import helper
from config import settings

def main():
    pass
""",
            path=Path("main.py"),
            language="python",
            version=1,
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc),
            task_id=uuid4(),
            agent_id=uuid4()
        )

    @pytest.mark.asyncio
    async def test_python_dependency_analysis(self, tracker, python_artifact):
        """Test Python dependency detection."""
        dependencies = await tracker.analyze_artifact(python_artifact)

        # Check that imports were detected
        import_paths = {dep.import_path for dep in dependencies}
        assert "os" in import_paths
        assert "json" in import_paths
        assert "pathlib.Path" in import_paths
        assert "utils.helper" in import_paths
        assert "config.settings" in import_paths

    @pytest.mark.asyncio
    async def test_javascript_dependency_analysis(self, tracker):
        """Test JavaScript dependency detection."""
        js_artifact = Artifact(
            id=uuid4(),
            name="app.js",
            type=ArtifactType.SOURCE_CODE,
            content="""import React from 'react';
import { useState } from 'react';
import './styles.css';
const utils = require('./utils');
const { helper } = require('./helpers');

export default function App() {
    return null;
}
""",
            path=Path("app.js"),
            language="javascript",
            version=1,
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc),
            task_id=uuid4(),
            agent_id=uuid4()
        )

        dependencies = await tracker.analyze_artifact(js_artifact)
        import_paths = {dep.import_path for dep in dependencies}

        assert "react" in import_paths
        assert "./styles.css" in import_paths
        assert "./utils" in import_paths
        assert "./helpers" in import_paths

    @pytest.mark.asyncio
    async def test_add_dependency(self, tracker):
        """Test manual dependency addition."""
        source_id = uuid4()
        target_id = uuid4()

        dep = await tracker.add_dependency(
            source_id,
            target_id,
            dependency_type="import",
            metadata={"critical": True}
        )

        assert dep.source_id == source_id
        assert dep.target_id == target_id
        assert dep.metadata["critical"] is True

        # Check dependency was added to graph
        deps = await tracker.get_dependencies(source_id)
        assert target_id in deps

    @pytest.mark.asyncio
    async def test_cyclic_dependency_detection(self, tracker):
        """Test detection of cyclic dependencies."""
        # Create a cycle: A -> B -> C -> A
        a_id, b_id, c_id = uuid4(), uuid4(), uuid4()

        await tracker.add_dependency(a_id, b_id)
        await tracker.add_dependency(b_id, c_id)

        # This should raise CyclicDependencyError
        with pytest.raises(CyclicDependencyError) as exc_info:
            await tracker.add_dependency(c_id, a_id)

        # Verify the cycle was detected
        assert "Cyclic dependency detected" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_dependencies_recursive(self, tracker):
        """Test recursive dependency retrieval."""
        # Create chain: A -> B -> C -> D
        a_id, b_id, c_id, d_id = uuid4(), uuid4(), uuid4(), uuid4()

        await tracker.add_dependency(a_id, b_id)
        await tracker.add_dependency(b_id, c_id)
        await tracker.add_dependency(c_id, d_id)

        # Get direct dependencies
        direct_deps = await tracker.get_dependencies(a_id, recursive=False)
        assert direct_deps == {b_id}

        # Get all dependencies
        all_deps = await tracker.get_dependencies(a_id, recursive=True)
        assert all_deps == {b_id, c_id, d_id}

    @pytest.mark.asyncio
    async def test_impact_analysis(self, tracker):
        """Test impact analysis for changes."""
        # Create dependency tree
        #     A
        #    / \
        #   B   C
        #  /
        # D
        a_id, b_id, c_id, d_id = uuid4(), uuid4(), uuid4(), uuid4()

        await tracker.add_dependency(b_id, a_id)
        await tracker.add_dependency(c_id, a_id)
        await tracker.add_dependency(d_id, b_id)

        # Analyze impact of changing A
        impact = await tracker.get_impact_analysis(a_id)

        assert impact["direct_impact"] == 2  # B and C
        assert impact["total_impact"] == 3   # B, C, and D
        assert impact["risk_level"] == "low"  # 3 affected artifacts

    @pytest.mark.asyncio
    async def test_build_order(self, tracker):
        """Test topological build order."""
        # Create dependencies: A -> B, B -> C, D -> C
        a_id, b_id, c_id, d_id = uuid4(), uuid4(), uuid4(), uuid4()

        await tracker.add_dependency(a_id, b_id)
        await tracker.add_dependency(b_id, c_id)
        await tracker.add_dependency(d_id, c_id)

        # Get build order
        build_order = await tracker.get_build_order()

        # C should come before B and D
        # B should come before A
        c_index = build_order.index(c_id)
        b_index = build_order.index(b_id)
        a_index = build_order.index(a_id)
        d_index = build_order.index(d_id)

        assert c_index < b_index
        assert c_index < d_index
        assert b_index < a_index
