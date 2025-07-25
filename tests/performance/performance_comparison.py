"""
Performance comparison between original and optimized implementations.
"""

import asyncio
import json

# Configure logging
import logging
import time
import tracemalloc
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

import psutil

logging.basicConfig(level=logging.ERROR)

# Original implementations
from src.core.artifact_manager import ArtifactManager
from src.core.interfaces import AgentRole, Artifact, ArtifactType, Task, TaskPriority
from src.core.optimized_artifact_manager import OptimizedArtifactManager
from src.core.optimized_task_manager import OptimizedTaskManager
from src.core.task_manager import TaskManager
from src.storage.memory_storage import MemoryStorage

# Optimized implementations
from src.storage.optimized_memory_storage import OptimizedMemoryStorage


class PerformanceComparison:
    """Compare performance between original and optimized implementations."""

    def __init__(self):
        self.results = {}
        self.test_data_dir = Path("./performance_test_data")
        self.test_data_dir.mkdir(exist_ok=True)

    async def run_all_comparisons(self) -> Dict[str, Any]:
        """Run all performance comparisons."""
        print("Running performance comparisons...\n")

        comparisons = [
            self.compare_memory_storage,
            self.compare_task_management,
            self.compare_artifact_management,
        ]

        results = {}
        for comparison in comparisons:
            result = await comparison()
            results.update(result)

        self.results = results
        return results

    async def compare_memory_storage(self) -> Dict[str, Any]:
        """Compare memory storage implementations."""
        print("Comparing memory storage implementations...")

        # Create test artifacts
        test_artifacts = []
        for i in range(1000):
            artifact = Artifact(
                name=f"test_artifact_{i}.py",
                type=ArtifactType.SOURCE_CODE,
                content=f"# Test artifact {i}\nprint('Hello World {i}')\n" * 20,
                path=Path(f"test_artifact_{i}.py"),
                language="python",
                task_id=uuid4(),
                agent_id=uuid4()
            )
            test_artifacts.append(artifact)

        # Test original implementation
        original_time, original_memory = await self._benchmark_memory_storage_original(test_artifacts)

        # Test optimized implementation
        optimized_time, optimized_memory = await self._benchmark_memory_storage_optimized(test_artifacts)

        # Calculate improvements
        time_improvement = ((original_time - optimized_time) / original_time) * 100
        memory_improvement = ((original_memory - optimized_memory) / original_memory) * 100

        result = {
            "memory_storage": {
                "original": {"time": original_time, "memory": original_memory},
                "optimized": {"time": optimized_time, "memory": optimized_memory},
                "improvements": {
                    "time_improvement_percent": time_improvement,
                    "memory_improvement_percent": memory_improvement,
                    "throughput_improvement": (1000 / optimized_time) / (1000 / original_time)
                }
            }
        }

        print(f"  Original: {original_time:.3f}s, {original_memory:.2f}MB")
        print(f"  Optimized: {optimized_time:.3f}s, {optimized_memory:.2f}MB")
        print(f"  Improvement: {time_improvement:.1f}% faster, {memory_improvement:.1f}% less memory\n")

        return result

    async def compare_task_management(self) -> Dict[str, Any]:
        """Compare task management implementations."""
        print("Comparing task management implementations...")

        # Create test tasks with dependencies
        test_tasks = []
        for i in range(500):
            task = Task(
                name=f"Test Task {i}",
                description=f"Description for task {i}",
                priority=TaskPriority.MEDIUM,
                required_role=AgentRole.CORE_LOGIC,
                dependencies=[test_tasks[j].id for j in range(max(0, i-3), i)],
                metadata={"test_index": i}
            )
            test_tasks.append(task)

        # Test original implementation
        original_time, original_memory = await self._benchmark_task_management_original(test_tasks)

        # Test optimized implementation
        optimized_time, optimized_memory = await self._benchmark_task_management_optimized(test_tasks)

        # Calculate improvements
        time_improvement = ((original_time - optimized_time) / original_time) * 100
        memory_improvement = ((original_memory - optimized_memory) / original_memory) * 100

        result = {
            "task_management": {
                "original": {"time": original_time, "memory": original_memory},
                "optimized": {"time": optimized_time, "memory": optimized_memory},
                "improvements": {
                    "time_improvement_percent": time_improvement,
                    "memory_improvement_percent": memory_improvement,
                    "throughput_improvement": (500 / optimized_time) / (500 / original_time)
                }
            }
        }

        print(f"  Original: {original_time:.3f}s, {original_memory:.2f}MB")
        print(f"  Optimized: {optimized_time:.3f}s, {optimized_memory:.2f}MB")
        print(f"  Improvement: {time_improvement:.1f}% faster, {memory_improvement:.1f}% less memory\n")

        return result

    async def compare_artifact_management(self) -> Dict[str, Any]:
        """Compare artifact management implementations."""
        print("Comparing artifact management implementations...")

        # Create test artifacts
        test_artifacts = []
        for i in range(200):
            artifact = Artifact(
                name=f"artifact_{i}.py",
                type=ArtifactType.SOURCE_CODE,
                content=f"# Artifact {i}\nprint('Test {i}')\n" * 50,
                path=Path(f"artifact_{i}.py"),
                language="python",
                task_id=uuid4(),
                agent_id=uuid4(),
                metadata={"test_index": i}
            )
            test_artifacts.append(artifact)

        # Test original implementation
        original_time, original_memory = await self._benchmark_artifact_management_original(test_artifacts)

        # Test optimized implementation
        optimized_time, optimized_memory = await self._benchmark_artifact_management_optimized(test_artifacts)

        # Calculate improvements
        time_improvement = ((original_time - optimized_time) / original_time) * 100
        memory_improvement = ((original_memory - optimized_memory) / original_memory) * 100

        result = {
            "artifact_management": {
                "original": {"time": original_time, "memory": original_memory},
                "optimized": {"time": optimized_time, "memory": optimized_memory},
                "improvements": {
                    "time_improvement_percent": time_improvement,
                    "memory_improvement_percent": memory_improvement,
                    "throughput_improvement": (200 / optimized_time) / (200 / original_time)
                }
            }
        }

        print(f"  Original: {original_time:.3f}s, {original_memory:.2f}MB")
        print(f"  Optimized: {optimized_time:.3f}s, {optimized_memory:.2f}MB")
        print(f"  Improvement: {time_improvement:.1f}% faster, {memory_improvement:.1f}% less memory\n")

        return result

    async def _benchmark_memory_storage_original(self, artifacts: List[Artifact]) -> tuple:
        """Benchmark original memory storage."""
        tracemalloc.start()
        process = psutil.Process()
        start_memory = process.memory_info().rss / 1024 / 1024

        storage = MemoryStorage(max_size=len(artifacts))

        start_time = time.perf_counter()

        # Store artifacts
        for artifact in artifacts:
            await storage.store(artifact)

        # Retrieve artifacts
        for artifact in artifacts:
            await storage.get(artifact.id)

        end_time = time.perf_counter()

        end_memory = process.memory_info().rss / 1024 / 1024
        tracemalloc.stop()

        return end_time - start_time, end_memory - start_memory

    async def _benchmark_memory_storage_optimized(self, artifacts: List[Artifact]) -> tuple:
        """Benchmark optimized memory storage."""
        tracemalloc.start()
        process = psutil.Process()
        start_memory = process.memory_info().rss / 1024 / 1024

        storage = OptimizedMemoryStorage(max_size=len(artifacts))
        await storage.initialize()

        start_time = time.perf_counter()

        # Store artifacts in batches
        await storage.store_batch(artifacts)

        # Retrieve artifacts in batches
        artifact_ids = [a.id for a in artifacts]
        await storage.get_batch(artifact_ids)

        end_time = time.perf_counter()

        await storage.shutdown()

        end_memory = process.memory_info().rss / 1024 / 1024
        tracemalloc.stop()

        return end_time - start_time, end_memory - start_memory

    async def _benchmark_task_management_original(self, tasks: List[Task]) -> tuple:
        """Benchmark original task management."""
        tracemalloc.start()
        process = psutil.Process()
        start_memory = process.memory_info().rss / 1024 / 1024

        task_manager = TaskManager()

        start_time = time.perf_counter()

        # Add tasks
        await task_manager.add_tasks(tasks)

        # Simulate task execution
        completed_count = 0
        while completed_count < len(tasks):
            ready_tasks = await task_manager.get_next_tasks()
            for task in ready_tasks:
                await task_manager.start_task(task.id)
                await task_manager.complete_task(task.id, [])
                completed_count += 1

        end_time = time.perf_counter()

        end_memory = process.memory_info().rss / 1024 / 1024
        tracemalloc.stop()

        return end_time - start_time, end_memory - start_memory

    async def _benchmark_task_management_optimized(self, tasks: List[Task]) -> tuple:
        """Benchmark optimized task management."""
        tracemalloc.start()
        process = psutil.Process()
        start_memory = process.memory_info().rss / 1024 / 1024

        task_manager = OptimizedTaskManager()

        start_time = time.perf_counter()

        # Add tasks in batch
        await task_manager.add_tasks(tasks)

        # Simulate task execution
        completed_count = 0
        while completed_count < len(tasks):
            ready_tasks = await task_manager.get_next_tasks()
            for task in ready_tasks:
                await task_manager.start_task(task.id)
                await task_manager.complete_task(task.id, "result")
                completed_count += 1

        end_time = time.perf_counter()

        end_memory = process.memory_info().rss / 1024 / 1024
        tracemalloc.stop()

        return end_time - start_time, end_memory - start_memory

    async def _benchmark_artifact_management_original(self, artifacts: List[Artifact]) -> tuple:
        """Benchmark original artifact management."""
        tracemalloc.start()
        process = psutil.Process()
        start_memory = process.memory_info().rss / 1024 / 1024

        storage_path = self.test_data_dir / "original_artifacts"
        storage_path.mkdir(exist_ok=True)

        artifact_manager = ArtifactManager(
            storage_path=storage_path,
            max_memory_cache_size=len(artifacts)
        )
        await artifact_manager.initialize()

        start_time = time.perf_counter()

        # Store artifacts
        for artifact in artifacts:
            await artifact_manager.store_artifact(artifact)

        # Retrieve artifacts
        for artifact in artifacts:
            await artifact_manager.get_artifact(artifact.id)

        end_time = time.perf_counter()

        end_memory = process.memory_info().rss / 1024 / 1024
        tracemalloc.stop()

        return end_time - start_time, end_memory - start_memory

    async def _benchmark_artifact_management_optimized(self, artifacts: List[Artifact]) -> tuple:
        """Benchmark optimized artifact management."""
        tracemalloc.start()
        process = psutil.Process()
        start_memory = process.memory_info().rss / 1024 / 1024

        storage_path = self.test_data_dir / "optimized_artifacts"
        storage_path.mkdir(exist_ok=True)

        artifact_manager = OptimizedArtifactManager(
            storage_path=storage_path,
            max_memory_cache_size=len(artifacts)
        )
        await artifact_manager.initialize()

        start_time = time.perf_counter()

        # Store artifacts in batch
        await artifact_manager.store_artifacts_batch(artifacts)

        # Retrieve artifacts in batch
        artifact_ids = [a.id for a in artifacts]
        await artifact_manager.get_artifacts_batch(artifact_ids)

        end_time = time.perf_counter()

        await artifact_manager.shutdown()

        end_memory = process.memory_info().rss / 1024 / 1024
        tracemalloc.stop()

        return end_time - start_time, end_memory - start_memory

    def generate_report(self) -> str:
        """Generate performance comparison report."""
        report = ["Performance Optimization Results", "=" * 40, ""]

        for component, data in self.results.items():
            report.append(f"{component.replace('_', ' ').title()}:")
            report.append(f"  Original: {data['original']['time']:.3f}s, {data['original']['memory']:.2f}MB")
            report.append(f"  Optimized: {data['optimized']['time']:.3f}s, {data['optimized']['memory']:.2f}MB")
            report.append(f"  Time Improvement: {data['improvements']['time_improvement_percent']:.1f}%")
            report.append(f"  Memory Improvement: {data['improvements']['memory_improvement_percent']:.1f}%")
            report.append(f"  Throughput Improvement: {data['improvements']['throughput_improvement']:.1f}x")
            report.append("")

        # Overall summary
        avg_time_improvement = sum(
            data['improvements']['time_improvement_percent']
            for data in self.results.values()
        ) / len(self.results)

        avg_memory_improvement = sum(
            data['improvements']['memory_improvement_percent']
            for data in self.results.values()
        ) / len(self.results)

        avg_throughput_improvement = sum(
            data['improvements']['throughput_improvement']
            for data in self.results.values()
        ) / len(self.results)

        report.extend([
            "Overall Summary:",
            f"  Average Time Improvement: {avg_time_improvement:.1f}%",
            f"  Average Memory Improvement: {avg_memory_improvement:.1f}%",
            f"  Average Throughput Improvement: {avg_throughput_improvement:.1f}x",
            ""
        ])

        return "\n".join(report)

    def save_results(self, file_path: Path) -> None:
        """Save results to file."""
        with open(file_path, 'w') as f:
            json.dump(self.results, f, indent=2)


async def main():
    """Run performance comparison."""
    print("Performance Optimization Analysis")
    print("=" * 40)

    comparison = PerformanceComparison()
    results = await comparison.run_all_comparisons()

    # Generate and display report
    report = comparison.generate_report()
    print(report)

    # Save results
    comparison.save_results(Path("optimization_results.json"))

    # Save report
    with open("optimization_report.txt", "w") as f:
        f.write(report)

    print("Results saved to optimization_results.json")
    print("Report saved to optimization_report.txt")


if __name__ == "__main__":
    asyncio.run(main())
