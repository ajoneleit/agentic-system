"""
Performance benchmark for WorkspaceIndex.

This script demonstrates the performance characteristics of the WorkspaceIndex
and provides benchmarks for various operations.
"""

import time
import tempfile
from pathlib import Path
import random
import string
from typing import List, Tuple

from src.core.workspace_index import WorkspaceIndex, index_workspace


def create_test_workspace(root: Path, file_count: int, dir_depth: int = 3) -> int:
    """
    Create a test workspace with specified number of files.
    
    Returns the actual number of files created.
    """
    files_created = 0
    files_per_dir = max(1, file_count // (dir_depth * 10))
    
    # Create directory structure
    for i in range(dir_depth):
        for j in range(10):
            dir_path = root / f"level{i}" / f"dir{j}"
            dir_path.mkdir(parents=True, exist_ok=True)
            
            # Create files in this directory
            for k in range(files_per_dir):
                if files_created >= file_count:
                    return files_created
                
                # Mix of file types
                if k % 5 == 0:
                    file_name = f"module_{k}.py"
                    content = f"# Python module {k}\nprint('test')"
                elif k % 5 == 1:
                    file_name = f"test_{k}.py"
                    content = f"import pytest\n# Test {k}"
                elif k % 5 == 2:
                    file_name = f"doc_{k}.md"
                    content = f"# Documentation {k}\nSome content"
                elif k % 5 == 3:
                    file_name = f"data_{k}.json"
                    content = '{"key": "value"}'
                else:
                    file_name = f"file_{k}.txt"
                    content = ''.join(random.choices(string.ascii_letters, k=100))
                
                (dir_path / file_name).write_text(content)
                files_created += 1
    
    # Create some binary files
    for i in range(min(10, file_count // 100)):
        bin_file = root / f"binary_{i}.bin"
        bin_file.write_bytes(bytes(random.randint(0, 255) for _ in range(1000)))
        files_created += 1
    
    return files_created


def benchmark_indexing(file_counts: List[int]) -> List[Tuple[int, float, float]]:
    """Benchmark index building for different file counts."""
    results = []
    
    for file_count in file_counts:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            actual_count = create_test_workspace(root, file_count)
            
            # Benchmark index building
            start_time = time.time()
            index = index_workspace(root)
            duration = time.time() - start_time
            
            files_per_second = len(index) / duration
            
            results.append((actual_count, duration, files_per_second))
            
            print(f"Indexed {len(index)} files in {duration:.3f}s "
                  f"({files_per_second:.0f} files/sec)")
    
    return results


def benchmark_operations(index: WorkspaceIndex) -> dict:
    """Benchmark various index operations."""
    results = {}
    
    # Benchmark get_all_files
    start = time.time()
    all_files = index.get_all_files()
    results['get_all_files'] = time.time() - start
    
    # Benchmark get_files_by_extension
    start = time.time()
    py_files = index.get_files_by_extension('.py')
    results['get_files_by_extension'] = time.time() - start
    
    # Benchmark find_files with pattern
    start = time.time()
    test_files = index.find_files(pattern="test_*.py")
    results['find_files_pattern'] = time.time() - start
    
    # Benchmark find_files with multiple criteria
    start = time.time()
    filtered_files = index.find_files(
        extension='.py',
        is_binary=False,
        max_size=10000
    )
    results['find_files_multi'] = time.time() - start
    
    # Benchmark single file lookup
    if all_files:
        sample_file = random.choice(all_files)
        start = time.time()
        for _ in range(1000):
            index.get_file(sample_file.relative_path)
        results['get_file_1000x'] = time.time() - start
    
    return results


def main():
    """Run performance benchmarks."""
    print("WorkspaceIndex Performance Benchmark")
    print("=" * 50)
    
    # Test different file counts
    file_counts = [100, 500, 1000, 5000, 10000]
    
    print("\n1. Index Building Performance:")
    print("-" * 30)
    indexing_results = benchmark_indexing(file_counts)
    
    print("\n2. Operation Performance (10,000 files):")
    print("-" * 30)
    
    # Create a large workspace for operation benchmarks
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        print("Creating test workspace...")
        actual_count = create_test_workspace(root, 10000)
        print(f"Created {actual_count} files")
        
        # Build index
        print("Building index...")
        start = time.time()
        index = index_workspace(root)
        build_time = time.time() - start
        print(f"Index built in {build_time:.3f}s")
        
        # Benchmark operations
        print("\nBenchmarking operations...")
        op_results = benchmark_operations(index)
        
        for operation, duration in op_results.items():
            if operation == 'get_file_1000x':
                avg_time = duration / 1000 * 1000  # Convert to microseconds
                print(f"{operation}: {duration:.3f}s total, {avg_time:.1f}μs per lookup")
            else:
                print(f"{operation}: {duration:.6f}s")
        
        # Memory usage estimate
        import sys
        index_size = sys.getsizeof(index._index) + \
                    sys.getsizeof(index._extension_map) + \
                    sys.getsizeof(index._directory_map)
        print(f"\nApproximate memory usage: {index_size / (1024**2):.2f} MB")
        
        # Statistics
        print(f"\nIndex Statistics:")
        stats = index.stats
        for key, value in stats.items():
            if key == 'total_size':
                print(f"  {key}: {value / (1024**2):.2f} MB")
            elif key in ['last_index_time', 'index_duration']:
                continue
            else:
                print(f"  {key}: {value}")
    
    print("\n3. Summary:")
    print("-" * 30)
    print("File Count | Build Time | Files/sec")
    print("-" * 36)
    for count, duration, fps in indexing_results:
        print(f"{count:10d} | {duration:10.3f}s | {fps:9.0f}")
    
    # Performance assertions
    print("\nPerformance Targets:")
    target_1000 = next((r for r in indexing_results if r[0] >= 1000), None)
    if target_1000:
        if target_1000[1] < 0.5:
            print("✓ 1000 files indexed in < 500ms")
        else:
            print(f"✗ 1000 files took {target_1000[1]:.3f}s (target: < 500ms)")


if __name__ == "__main__":
    main()