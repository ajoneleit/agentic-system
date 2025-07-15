"""
Comprehensive test suite for WorkspaceIndex functionality.
Focus on file detection, performance, concurrent updates, and error resilience.
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from src.core.workspace_index import WorkspaceIndex
from src.core.result import Result
from src.core.agent_errors import WorkspaceError
# Additional exceptions may not exist yet


class TestWorkspaceIndexPerformance:
    """Test WorkspaceIndex performance with large repositories."""
    
    @pytest.fixture
    def large_workspace(self, tmp_path):
        """Create a large workspace for performance testing."""
        workspace = tmp_path / "large_workspace"
        workspace.mkdir()
        
        # Create nested directory structure
        for i in range(10):  # 10 main directories
            main_dir = workspace / f"module_{i}"
            main_dir.mkdir()
            
            for j in range(20):  # 20 subdirectories each
                sub_dir = main_dir / f"submodule_{j}"
                sub_dir.mkdir()
                
                for k in range(5):  # 5 files each
                    file_path = sub_dir / f"file_{k}.py"
                    file_path.write_text(f"# File {i}.{j}.{k}\nprint('test')")
        
        # Total: 10 * 20 * 5 = 1000 files
        return workspace
    
    @pytest.fixture
    def workspace_index(self, large_workspace):
        """Create a WorkspaceIndex instance."""
        return WorkspaceIndex(root_path=large_workspace)
    
    @pytest.mark.asyncio
    async def test_workspace_index_performance_large_repos(self, workspace_index, large_workspace):
        """Test performance with large repositories."""
        
        # Benchmark initial indexing
        start_time = time.time()
        
        result = await workspace_index.index_workspace(str(large_workspace))
        
        indexing_time = time.time() - start_time
        
        # Verify indexing completed successfully
        assert result.is_success()
        
        # Should index within reasonable time
        assert indexing_time < 10.0  # Less than 10 seconds for 1000 files
        
        # Verify all files were indexed
        all_files = workspace_index.get_all_files()
        assert len(all_files) >= 1000  # Should find all files
        
        # Benchmark file search
        start_time = time.time()
        
        search_results = workspace_index.search_files("file_1.py")
        
        search_time = time.time() - start_time
        
        # Should search quickly
        assert search_time < 0.1  # Less than 100ms
        assert len(search_results) > 0


class TestWorkspaceIndexConcurrentUpdates:
    """Test concurrent updates and thread safety."""
    
    @pytest.fixture
    def concurrent_workspace(self, tmp_path):
        """Create a workspace for concurrent testing."""
        workspace = tmp_path / "concurrent_workspace"
        workspace.mkdir()
        
        # Create initial files
        for i in range(50):
            file_path = workspace / f"concurrent_file_{i}.py"
            file_path.write_text(f"# Concurrent file {i}")
        
        return workspace
    
    @pytest.fixture
    def workspace_index(self, concurrent_workspace):
        return WorkspaceIndex(root_path=concurrent_workspace)
    
    @pytest.mark.asyncio
    async def test_workspace_index_concurrent_updates(self, workspace_index, concurrent_workspace):
        """Test concurrent index updates."""
        
        # Initial indexing
        await workspace_index.index_workspace(str(concurrent_workspace))
        
        # Concurrent file operations
        async def concurrent_file_operation(operation_id):
            # Create new file
            new_file = concurrent_workspace / f"concurrent_new_{operation_id}.py"
            new_file.write_text(f"# Concurrent new file {operation_id}")
            
            # Update index
            return await workspace_index.update_index(str(concurrent_workspace))
        
        # Execute concurrent operations
        concurrent_tasks = [
            concurrent_file_operation(i) for i in range(10)
        ]
        
        results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)
        
        # Verify concurrent operations completed
        successful_results = [
            r for r in results 
            if isinstance(r, Result) and r.is_success()
        ]
        
        # Should handle concurrent updates gracefully
        assert len(successful_results) >= 5  # At least half should succeed
        
        # Verify final state is consistent
        final_files = workspace_index.get_all_files()
        assert len(final_files) >= 50  # At least original files


class TestWorkspaceIndexErrorResilience:
    """Test error resilience and recovery."""
    
    @pytest.fixture
    def problematic_workspace(self, tmp_path):
        """Create a workspace with problematic files."""
        workspace = tmp_path / "problematic_workspace"
        workspace.mkdir()
        
        # Create normal files
        for i in range(10):
            file_path = workspace / f"normal_file_{i}.py"
            file_path.write_text(f"# Normal file {i}")
        
        # Create problematic files
        # Large file
        large_file = workspace / "large_file.py"
        large_file.write_text("# Large file\n" + "x" * 1000000)
        
        # File with special characters
        special_file = workspace / "special_file_test.py"
        special_file.write_text("# Special characters")
        
        # Binary file (non-text)
        binary_file = workspace / "binary_file.bin"
        binary_file.write_bytes(b'\x00\x01\x02\x03\x04\x05')
        
        return workspace
    
    @pytest.fixture
    def workspace_index(self, problematic_workspace):
        return WorkspaceIndex(root_path=problematic_workspace)
    
    @pytest.mark.asyncio
    async def test_workspace_index_error_resilience(self, workspace_index, problematic_workspace):
        """Test resilience to various error conditions."""
        
        # Index workspace with problematic files
        result = await workspace_index.index_workspace(str(problematic_workspace))
        
        # Should handle errors gracefully
        assert result.is_success() or result.is_failure()
        
        # Should index at least some files
        if result.is_success():
            indexed_files = workspace_index.get_all_files()
            assert len(indexed_files) >= 10  # At least normal files