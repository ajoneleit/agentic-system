"""
Performance benchmark tests for the agentic system.

This module contains performance tests to measure and track optimization improvements.
"""

import asyncio
import time
import json
import statistics
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from uuid import uuid4
import psutil
import tracemalloc
from contextlib import asynccontextmanager

from src.core.artifact_manager import ArtifactManager
from src.core.task_manager import TaskManager
from src.core.workspace_index import WorkspaceIndex
from src.core.interfaces import Artifact, ArtifactType, Task, TaskPriority, AgentRole
from src.agents.meta_agent import MetaAgent
from src.storage.memory_storage import MemoryStorage
from src.storage.filesystem_storage import FilesystemStorage


@dataclass
class PerformanceMetrics:
    """Container for performance measurements."""
    
    operation_name: str
    execution_time: float
    memory_usage: float  # in MB
    cpu_usage: float  # percentage
    memory_peak: float  # peak memory in MB
    iterations: int
    throughput: float  # operations per second
    metadata: Dict[str, Any]


class PerformanceBenchmark:
    """Performance benchmark suite for the agentic system."""
    
    def __init__(self, test_data_dir: Path = Path("./benchmark_data")):
        self.test_data_dir = test_data_dir
        self.test_data_dir.mkdir(exist_ok=True)
        self.results: List[PerformanceMetrics] = []
        
    async def run_all_benchmarks(self) -> Dict[str, PerformanceMetrics]:
        """Run all performance benchmarks."""
        benchmarks = {
            "artifact_storage": self.benchmark_artifact_storage,
            "task_management": self.benchmark_task_management,
            "workspace_indexing": self.benchmark_workspace_indexing,
            "memory_storage": self.benchmark_memory_storage,
            "task_decomposition": self.benchmark_task_decomposition,
            "agent_spawning": self.benchmark_agent_spawning,
        }
        
        results = {}
        for name, benchmark_func in benchmarks.items():
            print(f"Running benchmark: {name}")
            result = await benchmark_func()
            results[name] = result
            self.results.append(result)
            print(f"✓ {name}: {result.execution_time:.3f}s, {result.memory_usage:.2f}MB")
        
        return results
    
    @asynccontextmanager
    async def measure_performance(self, operation_name: str, iterations: int = 1):
        """Context manager to measure performance of operations."""
        # Start monitoring
        tracemalloc.start()
        process = psutil.Process()
        
        # Initial measurements
        start_time = time.perf_counter()
        start_memory = process.memory_info().rss / 1024 / 1024  # MB
        start_cpu = process.cpu_percent()
        
        # Let CPU measurement stabilize
        await asyncio.sleep(0.1)
        
        try:
            yield
        finally:
            # Final measurements
            end_time = time.perf_counter()
            end_memory = process.memory_info().rss / 1024 / 1024  # MB
            end_cpu = process.cpu_percent()
            
            # Memory peak
            current, peak = tracemalloc.get_traced_memory()
            peak_mb = peak / 1024 / 1024  # MB
            tracemalloc.stop()
            
            # Calculate metrics
            execution_time = end_time - start_time
            memory_usage = end_memory - start_memory
            cpu_usage = end_cpu - start_cpu
            throughput = iterations / execution_time if execution_time > 0 else 0
            
            # Store results
            metrics = PerformanceMetrics(
                operation_name=operation_name,
                execution_time=execution_time,
                memory_usage=memory_usage,
                cpu_usage=cpu_usage,
                memory_peak=peak_mb,
                iterations=iterations,
                throughput=throughput,
                metadata={}
            )
            
            self.results.append(metrics)
    
    async def benchmark_artifact_storage(self) -> PerformanceMetrics:
        """Benchmark artifact storage operations."""
        storage_path = self.test_data_dir / "artifacts"
        storage_path.mkdir(exist_ok=True)
        
        # Create artifact manager
        artifact_manager = ArtifactManager(
            storage_path=storage_path,
            max_memory_cache_size=100,
            enable_compression=True
        )
        await artifact_manager.initialize()
        
        # Create test artifacts
        test_artifacts = []
        for i in range(100):
            artifact = Artifact(
                name=f"test_artifact_{i}.py",
                type=ArtifactType.SOURCE_CODE,
                content=f"# Test artifact {i}\nprint('Hello World {i}')\n" * 10,
                path=Path(f"test_artifact_{i}.py"),
                language="python",
                task_id=uuid4(),
                agent_id=uuid4(),
                metadata={"test_index": i}
            )
            test_artifacts.append(artifact)
        
        # Benchmark storage operations
        async with self.measure_performance("artifact_storage", 100):
            # Store artifacts
            for artifact in test_artifacts:
                await artifact_manager.store_artifact(artifact)
            
            # Retrieve artifacts
            for artifact in test_artifacts:
                retrieved = await artifact_manager.get_artifact(artifact.id)
                assert retrieved.content == artifact.content
        
        # Get metrics
        metrics = await artifact_manager.get_metrics()
        
        return PerformanceMetrics(
            operation_name="artifact_storage",
            execution_time=self.results[-1].execution_time,
            memory_usage=self.results[-1].memory_usage,
            cpu_usage=self.results[-1].cpu_usage,
            memory_peak=self.results[-1].memory_peak,
            iterations=100,
            throughput=self.results[-1].throughput,
            metadata={
                "cache_hit_rate": metrics.get("cache_hit_rate", 0),
                "total_artifacts": metrics.get("total_artifacts", 0),
                "cache_size": metrics.get("cache_size", 0)
            }
        )
    
    async def benchmark_task_management(self) -> PerformanceMetrics:
        """Benchmark task management operations."""
        task_manager = TaskManager()
        
        # Create test tasks
        test_tasks = []
        for i in range(50):
            task = Task(
                name=f"Test Task {i}",
                description=f"Description for task {i}",
                priority=TaskPriority.MEDIUM,
                required_role=AgentRole.CORE_LOGIC,
                dependencies=[test_tasks[j].id for j in range(max(0, i-2), i)],  # Depends on previous 2 tasks
                metadata={"test_index": i}
            )
            test_tasks.append(task)
        
        # Benchmark task operations
        async with self.measure_performance("task_management", 50):
            # Add tasks
            await task_manager.add_tasks(test_tasks)
            
            # Get ready tasks and complete them
            completed_count = 0
            while completed_count < len(test_tasks):
                ready_tasks = await task_manager.get_next_tasks()
                for task in ready_tasks:
                    await task_manager.start_task(task.id)
                    await task_manager.complete_task(task.id, [])
                    completed_count += 1
        
        # Get progress
        progress = await task_manager.get_progress()
        
        return PerformanceMetrics(
            operation_name="task_management",
            execution_time=self.results[-1].execution_time,
            memory_usage=self.results[-1].memory_usage,
            cpu_usage=self.results[-1].cpu_usage,
            memory_peak=self.results[-1].memory_peak,
            iterations=50,
            throughput=self.results[-1].throughput,
            metadata={
                "completed_tasks": progress.get("completed_tasks", 0),
                "total_tasks": progress.get("total_tasks", 0),
                "dependency_resolution_time": progress.get("dependency_resolution_time", 0)
            }
        )
    
    async def benchmark_workspace_indexing(self) -> PerformanceMetrics:
        """Benchmark workspace indexing operations."""
        workspace_path = self.test_data_dir / "workspace"
        workspace_path.mkdir(exist_ok=True)
        
        # Create test files
        test_files = []
        for i in range(100):
            file_path = workspace_path / f"test_file_{i}.py"
            file_path.write_text(f"# Test file {i}\nprint('Hello {i}')\n")
            test_files.append(file_path)
        
        # Create workspace index
        workspace_index = WorkspaceIndex(workspace_path)
        
        # Benchmark indexing operations
        async with self.measure_performance("workspace_indexing", 100):
            # Build index
            await workspace_index.build_index()
            
            # Search operations
            for i in range(0, 100, 10):
                results = await workspace_index.search_files(f"test_file_{i}")
                assert len(results) > 0
        
        # Get index stats
        stats = await workspace_index.get_stats()
        
        return PerformanceMetrics(
            operation_name="workspace_indexing",
            execution_time=self.results[-1].execution_time,
            memory_usage=self.results[-1].memory_usage,
            cpu_usage=self.results[-1].cpu_usage,
            memory_peak=self.results[-1].memory_peak,
            iterations=100,
            throughput=self.results[-1].throughput,
            metadata={
                "total_files": stats.get("total_files", 0),
                "indexed_files": stats.get("indexed_files", 0),
                "index_size": stats.get("index_size", 0)
            }
        )
    
    async def benchmark_memory_storage(self) -> PerformanceMetrics:
        """Benchmark memory storage operations."""
        memory_storage = MemoryStorage(max_size=1000)
        
        # Create test artifacts
        test_artifacts = []
        for i in range(500):
            artifact = Artifact(
                name=f"memory_test_{i}.py",
                type=ArtifactType.SOURCE_CODE,
                content=f"# Memory test {i}\n" * 20,
                path=Path(f"memory_test_{i}.py"),
                language="python",
                task_id=uuid4(),
                agent_id=uuid4()
            )
            test_artifacts.append(artifact)
        
        # Benchmark memory operations
        async with self.measure_performance("memory_storage", 500):
            # Store artifacts
            for artifact in test_artifacts:
                await memory_storage.store(artifact)
            
            # Retrieve artifacts
            for artifact in test_artifacts:
                retrieved = await memory_storage.get(artifact.id)
                if retrieved:  # Some might be evicted due to LRU
                    assert retrieved.content == artifact.content
        
        # Get storage stats
        size = await memory_storage.size()
        
        return PerformanceMetrics(
            operation_name="memory_storage",
            execution_time=self.results[-1].execution_time,
            memory_usage=self.results[-1].memory_usage,
            cpu_usage=self.results[-1].cpu_usage,
            memory_peak=self.results[-1].memory_peak,
            iterations=500,
            throughput=self.results[-1].throughput,
            metadata={
                "final_cache_size": size,
                "cache_evictions": max(0, 500 - size)
            }
        )
    
    async def benchmark_task_decomposition(self) -> PerformanceMetrics:
        """Benchmark task decomposition operations."""
        # This is a simplified benchmark since it depends on AI calls
        # In a real scenario, we'd mock the AI client
        
        test_requests = [
            "Create a simple calculator",
            "Build a todo list app",
            "Write a weather client",
            "Implement a file organizer",
            "Create a password generator"
        ]
        
        async with self.measure_performance("task_decomposition", len(test_requests)):
            # Simulate task decomposition timing
            for request in test_requests:
                # Simulate AI processing time
                await asyncio.sleep(0.1)
                
                # Simulate task creation
                tasks = []
                for i in range(3):  # Average 3 tasks per request
                    task = Task(
                        name=f"Task {i} for {request[:20]}",
                        description=f"Subtask {i}",
                        priority=TaskPriority.MEDIUM,
                        required_role=AgentRole.CORE_LOGIC
                    )
                    tasks.append(task)
        
        return PerformanceMetrics(
            operation_name="task_decomposition",
            execution_time=self.results[-1].execution_time,
            memory_usage=self.results[-1].memory_usage,
            cpu_usage=self.results[-1].cpu_usage,
            memory_peak=self.results[-1].memory_peak,
            iterations=len(test_requests),
            throughput=self.results[-1].throughput,
            metadata={
                "avg_tasks_per_request": 3,
                "total_requests": len(test_requests)
            }
        )
    
    async def benchmark_agent_spawning(self) -> PerformanceMetrics:
        """Benchmark agent spawning operations."""
        # Create a temporary meta agent for testing
        meta_agent = MetaAgent(artifact_storage_path=self.test_data_dir / "agents")
        
        # Simulate agent spawning
        async with self.measure_performance("agent_spawning", 10):
            for i in range(10):
                # Simulate agent creation time
                await asyncio.sleep(0.05)
                
                # Simulate agent initialization
                agent_data = {
                    "id": str(uuid4()),
                    "role": AgentRole.CORE_LOGIC,
                    "status": "ready",
                    "capabilities": ["code_generation", "testing"]
                }
        
        return PerformanceMetrics(
            operation_name="agent_spawning",
            execution_time=self.results[-1].execution_time,
            memory_usage=self.results[-1].memory_usage,
            cpu_usage=self.results[-1].cpu_usage,
            memory_peak=self.results[-1].memory_peak,
            iterations=10,
            throughput=self.results[-1].throughput,
            metadata={
                "agents_spawned": 10,
                "avg_spawn_time": self.results[-1].execution_time / 10
            }
        )
    
    def save_results(self, file_path: Path) -> None:
        """Save benchmark results to a file."""
        results_data = []
        for result in self.results:
            results_data.append({
                "operation_name": result.operation_name,
                "execution_time": result.execution_time,
                "memory_usage": result.memory_usage,
                "cpu_usage": result.cpu_usage,
                "memory_peak": result.memory_peak,
                "iterations": result.iterations,
                "throughput": result.throughput,
                "metadata": result.metadata
            })
        
        with open(file_path, 'w') as f:
            json.dump(results_data, f, indent=2)
    
    def generate_report(self) -> str:
        """Generate a performance report."""
        report = ["Performance Benchmark Report", "=" * 40, ""]
        
        for result in self.results:
            report.extend([
                f"Operation: {result.operation_name}",
                f"  Execution Time: {result.execution_time:.3f}s",
                f"  Memory Usage: {result.memory_usage:.2f}MB",
                f"  CPU Usage: {result.cpu_usage:.1f}%",
                f"  Memory Peak: {result.memory_peak:.2f}MB",
                f"  Iterations: {result.iterations}",
                f"  Throughput: {result.throughput:.2f} ops/sec",
                f"  Metadata: {result.metadata}",
                ""
            ])
        
        # Summary statistics
        avg_time = statistics.mean(r.execution_time for r in self.results)
        avg_memory = statistics.mean(r.memory_usage for r in self.results)
        total_throughput = sum(r.throughput for r in self.results)
        
        report.extend([
            "Summary Statistics:",
            f"  Average Execution Time: {avg_time:.3f}s",
            f"  Average Memory Usage: {avg_memory:.2f}MB",
            f"  Total Throughput: {total_throughput:.2f} ops/sec",
            ""
        ])
        
        return "\n".join(report)


async def main():
    """Run performance benchmarks."""
    print("Starting performance benchmarks...")
    
    benchmark = PerformanceBenchmark()
    results = await benchmark.run_all_benchmarks()
    
    # Save results
    results_file = Path("benchmark_results.json")
    benchmark.save_results(results_file)
    
    # Generate report
    report = benchmark.generate_report()
    print("\n" + report)
    
    # Save report
    report_file = Path("benchmark_report.txt")
    report_file.write_text(report)
    
    print(f"\nResults saved to {results_file}")
    print(f"Report saved to {report_file}")


if __name__ == "__main__":
    asyncio.run(main())