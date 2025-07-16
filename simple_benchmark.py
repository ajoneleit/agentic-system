"""
Simple performance benchmark for key operations.
"""

import asyncio
import time
import json
from pathlib import Path
from typing import Dict, List, Any
from uuid import uuid4
import psutil
import tracemalloc

# Configure logging to avoid issues
import logging
logging.basicConfig(level=logging.ERROR)

from src.core.interfaces import Artifact, ArtifactType, Task, TaskPriority, AgentRole
from src.storage.memory_storage import MemoryStorage


class SimpleBenchmark:
    """Simple performance benchmark."""
    
    def __init__(self):
        self.results = {}
    
    async def measure_operation(self, name: str, operation, iterations: int = 1):
        """Measure a single operation."""
        print(f"Benchmarking {name}...")
        
        # Setup monitoring
        tracemalloc.start()
        process = psutil.Process()
        
        # Initial measurements
        start_time = time.perf_counter()
        start_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Run operation
        for i in range(iterations):
            await operation()
        
        # Final measurements
        end_time = time.perf_counter()
        end_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Memory peak
        current, peak = tracemalloc.get_traced_memory()
        peak_mb = peak / 1024 / 1024  # MB
        tracemalloc.stop()
        
        # Calculate metrics
        execution_time = end_time - start_time
        memory_usage = end_memory - start_memory
        throughput = iterations / execution_time if execution_time > 0 else 0
        
        result = {
            "execution_time": execution_time,
            "memory_usage": memory_usage,
            "memory_peak": peak_mb,
            "iterations": iterations,
            "throughput": throughput
        }
        
        self.results[name] = result
        print(f"  Time: {execution_time:.3f}s, Memory: {memory_usage:.2f}MB, Throughput: {throughput:.1f} ops/sec")
        return result
    
    async def benchmark_memory_storage(self):
        """Benchmark memory storage operations."""
        storage = MemoryStorage(max_size=100)
        
        # Create test artifacts
        artifacts = []
        for i in range(100):
            artifact = Artifact(
                name=f"test_{i}.py",
                type=ArtifactType.SOURCE_CODE,
                content=f"print('Test {i}')\n" * 10,
                path=Path(f"test_{i}.py"),
                language="python",
                task_id=uuid4(),
                agent_id=uuid4()
            )
            artifacts.append(artifact)
        
        async def operation():
            # Store all artifacts
            for artifact in artifacts:
                await storage.store(artifact)
            
            # Retrieve all artifacts
            for artifact in artifacts:
                await storage.get(artifact.id)
        
        await self.measure_operation("memory_storage", operation)
    
    async def benchmark_task_creation(self):
        """Benchmark task creation and management."""
        async def operation():
            tasks = []
            for i in range(50):
                task = Task(
                    name=f"Task {i}",
                    description=f"Test task {i}",
                    priority=TaskPriority.MEDIUM,
                    required_role=AgentRole.CORE_LOGIC,
                    dependencies=[],
                    metadata={"index": i}
                )
                tasks.append(task)
            
            # Simulate some operations on tasks
            for task in tasks:
                _ = task.id
                _ = task.name
                _ = task.description
        
        await self.measure_operation("task_creation", operation)
    
    async def benchmark_artifact_serialization(self):
        """Benchmark artifact serialization/deserialization."""
        # Create test artifacts
        artifacts = []
        for i in range(100):
            artifact = Artifact(
                name=f"serialize_test_{i}.py",
                type=ArtifactType.SOURCE_CODE,
                content=f"# Serialization test {i}\n" * 50,
                path=Path(f"serialize_test_{i}.py"),
                language="python",
                task_id=uuid4(),
                agent_id=uuid4(),
                metadata={"test": True, "index": i}
            )
            artifacts.append(artifact)
        
        async def operation():
            # Serialize artifacts
            serialized = []
            for artifact in artifacts:
                data = {
                    "id": str(artifact.id),
                    "name": artifact.name,
                    "type": artifact.type.value,
                    "content": artifact.content,
                    "path": str(artifact.path),
                    "language": artifact.language,
                    "task_id": str(artifact.task_id),
                    "agent_id": str(artifact.agent_id),
                    "metadata": artifact.metadata
                }
                serialized.append(json.dumps(data))
            
            # Deserialize artifacts
            for data_str in serialized:
                data = json.loads(data_str)
                # Simulate reconstruction
                _ = data["id"]
                _ = data["name"]
                _ = data["content"]
        
        await self.measure_operation("artifact_serialization", operation)
    
    async def benchmark_file_operations(self):
        """Benchmark file I/O operations."""
        test_dir = Path("./benchmark_temp")
        test_dir.mkdir(exist_ok=True)
        
        async def operation():
            # Create files
            for i in range(50):
                file_path = test_dir / f"test_file_{i}.txt"
                content = f"Test file {i}\n" * 100
                file_path.write_text(content)
            
            # Read files
            for i in range(50):
                file_path = test_dir / f"test_file_{i}.txt"
                _ = file_path.read_text()
            
            # Clean up
            for i in range(50):
                file_path = test_dir / f"test_file_{i}.txt"
                file_path.unlink()
        
        await self.measure_operation("file_operations", operation)
        
        # Clean up
        if test_dir.exists():
            test_dir.rmdir()
    
    async def benchmark_dependency_checking(self):
        """Benchmark dependency resolution."""
        # Create tasks with dependencies
        tasks = []
        for i in range(100):
            task = Task(
                name=f"Dep Task {i}",
                description=f"Task with dependencies {i}",
                priority=TaskPriority.MEDIUM,
                required_role=AgentRole.CORE_LOGIC,
                dependencies=[tasks[j].id for j in range(max(0, i-3), i)],  # Depends on previous 3 tasks
                metadata={"index": i}
            )
            tasks.append(task)
        
        async def operation():
            # Simulate dependency checking
            for task in tasks:
                # Check if dependencies are met
                ready = True
                for dep_id in task.dependencies:
                    # Simulate dependency lookup
                    dep_found = any(t.id == dep_id for t in tasks)
                    if not dep_found:
                        ready = False
                        break
                
                # Simulate task readiness calculation
                if ready:
                    _ = task.name
        
        await self.measure_operation("dependency_checking", operation)
    
    async def run_all_benchmarks(self):
        """Run all benchmarks."""
        print("Running performance benchmarks...\n")
        
        await self.benchmark_memory_storage()
        await self.benchmark_task_creation()
        await self.benchmark_artifact_serialization()
        await self.benchmark_file_operations()
        await self.benchmark_dependency_checking()
        
        print("\nBenchmark Results:")
        print("=" * 50)
        
        for name, result in self.results.items():
            print(f"{name}:")
            print(f"  Execution Time: {result['execution_time']:.3f}s")
            print(f"  Memory Usage: {result['memory_usage']:.2f}MB")
            print(f"  Memory Peak: {result['memory_peak']:.2f}MB")
            print(f"  Throughput: {result['throughput']:.1f} ops/sec")
            print()
    
    def save_results(self, file_path: Path):
        """Save results to file."""
        with open(file_path, 'w') as f:
            json.dump(self.results, f, indent=2)


async def main():
    """Run the benchmark."""
    benchmark = SimpleBenchmark()
    await benchmark.run_all_benchmarks()
    
    # Save results
    benchmark.save_results(Path("baseline_results.json"))
    print("Results saved to baseline_results.json")


if __name__ == "__main__":
    asyncio.run(main())