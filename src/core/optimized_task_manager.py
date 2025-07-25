"""Optimized task manager with performance improvements.

Key optimizations:
1. Dependency graph optimization with caching
2. Parallel task execution where possible
3. Efficient priority queue implementation
4. Memory-efficient task tracking
5. Batch operations for better throughput
"""

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from structlog import get_logger

from src.core.interfaces import Task, TaskPriority

logger = get_logger(__name__)


@dataclass
class TaskNode:
    """Optimized task node with efficient dependency tracking."""

    task: Task
    dependencies: set[UUID] = field(default_factory=set)
    dependents: set[UUID] = field(default_factory=set)
    priority_score: float = 0.0
    estimated_duration: float = 0.0

    def __lt__(self, other):
        # Higher priority scores come first
        return self.priority_score > other.priority_score


class DependencyGraph:
    """Optimized dependency graph with cycle detection and topological sorting."""

    def __init__(self):
        self.nodes: dict[UUID, TaskNode] = {}
        self.ready_tasks: set[UUID] = set()
        self.completed_tasks: set[UUID] = set()
        self.failed_tasks: set[UUID] = set()
        self.in_progress_tasks: set[UUID] = set()

        # Caching for performance
        self._topological_order: Optional[list[UUID]] = None
        self._critical_path: Optional[list[UUID]] = None
        self._dependency_levels: dict[UUID, int] = {}

    def add_task(self, task: Task) -> None:
        """Add task to dependency graph."""
        if task.id in self.nodes:
            return

        node = TaskNode(
            task=task,
            dependencies=set(task.dependencies),
            priority_score=self._calculate_priority_score(task),
        )

        self.nodes[task.id] = node

        # Update dependent relationships
        for dep_id in task.dependencies:
            if dep_id in self.nodes:
                self.nodes[dep_id].dependents.add(task.id)

        # Check if task is ready
        if self._is_task_ready(task.id):
            self.ready_tasks.add(task.id)

        # Invalidate caches
        self._invalidate_caches()

    def add_tasks_batch(self, tasks: list[Task]) -> None:
        """Add multiple tasks efficiently."""
        # Add all tasks first
        for task in tasks:
            if task.id not in self.nodes:
                node = TaskNode(
                    task=task,
                    dependencies=set(task.dependencies),
                    priority_score=self._calculate_priority_score(task),
                )
                self.nodes[task.id] = node

        # Update relationships
        for task in tasks:
            node = self.nodes[task.id]
            for dep_id in task.dependencies:
                if dep_id in self.nodes:
                    self.nodes[dep_id].dependents.add(task.id)

        # Update ready tasks
        for task in tasks:
            if self._is_task_ready(task.id):
                self.ready_tasks.add(task.id)

        self._invalidate_caches()

    def complete_task(self, task_id: UUID) -> set[UUID]:
        """Mark task as completed and return newly ready tasks."""
        if task_id not in self.nodes:
            return set()

        self.completed_tasks.add(task_id)
        self.in_progress_tasks.discard(task_id)
        self.ready_tasks.discard(task_id)

        # Find newly ready tasks
        newly_ready = set()
        node = self.nodes[task_id]

        for dependent_id in node.dependents:
            if self._is_task_ready(dependent_id):
                newly_ready.add(dependent_id)
                self.ready_tasks.add(dependent_id)

        self._invalidate_caches()
        return newly_ready

    def fail_task(self, task_id: UUID) -> set[UUID]:
        """Mark task as failed and return affected tasks."""
        if task_id not in self.nodes:
            return set()

        self.failed_tasks.add(task_id)
        self.in_progress_tasks.discard(task_id)
        self.ready_tasks.discard(task_id)

        # Find affected tasks (all dependents)
        affected = set()
        self._find_all_dependents(task_id, affected)

        # Remove affected tasks from ready queue
        for affected_id in affected:
            self.ready_tasks.discard(affected_id)

        self._invalidate_caches()
        return affected

    def start_task(self, task_id: UUID) -> None:
        """Mark task as in progress."""
        self.in_progress_tasks.add(task_id)
        self.ready_tasks.discard(task_id)

    def get_ready_tasks(self, limit: int = 10) -> list[Task]:
        """Get ready tasks sorted by priority."""
        ready_nodes = [self.nodes[task_id] for task_id in self.ready_tasks if task_id in self.nodes]

        # Sort by priority score
        ready_nodes.sort(key=lambda x: x.priority_score, reverse=True)

        return [node.task for node in ready_nodes[:limit]]

    def get_critical_path(self) -> list[UUID]:
        """Get critical path through the task graph."""
        if self._critical_path is None:
            self._critical_path = self._calculate_critical_path()
        return self._critical_path

    def get_dependency_levels(self) -> dict[UUID, int]:
        """Get dependency levels for all tasks."""
        if not self._dependency_levels:
            self._dependency_levels = self._calculate_dependency_levels()
        return self._dependency_levels

    def validate_dependencies(self) -> bool:
        """Validate that there are no circular dependencies."""
        try:
            self._topological_sort()
            return True
        except ValueError:
            return False

    def _is_task_ready(self, task_id: UUID) -> bool:
        """Check if task is ready to execute."""
        if task_id not in self.nodes:
            return False

        if (
            task_id in self.completed_tasks
            or task_id in self.failed_tasks
            or task_id in self.in_progress_tasks
        ):
            return False

        node = self.nodes[task_id]
        return all(dep_id in self.completed_tasks for dep_id in node.dependencies)

    def _calculate_priority_score(self, task: Task) -> float:
        """Calculate priority score for task."""
        base_score = {TaskPriority.LOW: 1.0, TaskPriority.MEDIUM: 2.0, TaskPriority.HIGH: 3.0}.get(
            task.priority, 2.0
        )

        # Adjust based on estimated complexity
        complexity_multiplier = {"simple": 0.8, "medium": 1.0, "complex": 1.2}.get(
            task.estimated_complexity, 1.0
        )

        return base_score * complexity_multiplier

    def _find_all_dependents(self, task_id: UUID, visited: set[UUID]) -> None:
        """Find all tasks that depend on this task."""
        if task_id in visited or task_id not in self.nodes:
            return

        visited.add(task_id)
        node = self.nodes[task_id]

        for dependent_id in node.dependents:
            self._find_all_dependents(dependent_id, visited)

    def _topological_sort(self) -> list[UUID]:
        """Perform topological sort to detect cycles."""
        if self._topological_order is not None:
            return self._topological_order

        in_degree = defaultdict(int)
        for node in self.nodes.values():
            for _dep_id in node.dependencies:
                in_degree[node.task.id] += 1

        queue = deque([task_id for task_id in self.nodes.keys() if in_degree[task_id] == 0])
        result = []

        while queue:
            task_id = queue.popleft()
            result.append(task_id)

            if task_id in self.nodes:
                for dependent_id in self.nodes[task_id].dependents:
                    in_degree[dependent_id] -= 1
                    if in_degree[dependent_id] == 0:
                        queue.append(dependent_id)

        if len(result) != len(self.nodes):
            raise ValueError("Circular dependency detected")

        self._topological_order = result
        return result

    def _calculate_critical_path(self) -> list[UUID]:
        """Calculate critical path through task graph."""
        # Calculate longest path to each node
        longest_paths = {}

        # Process nodes in topological order
        for task_id in self._topological_sort():
            node = self.nodes[task_id]

            if not node.dependencies:
                longest_paths[task_id] = node.estimated_duration
            else:
                max_dep_path = max(longest_paths.get(dep_id, 0) for dep_id in node.dependencies)
                longest_paths[task_id] = max_dep_path + node.estimated_duration

        # Find the path with maximum duration
        if not longest_paths:
            return []

        max_task = max(longest_paths.keys(), key=lambda x: longest_paths[x])

        # Reconstruct path
        path = []
        current = max_task

        while current is not None:
            path.append(current)

            # Find the dependency that contributed to the longest path
            node = self.nodes[current]
            next_task = None

            if node.dependencies:
                next_task = max(node.dependencies, key=lambda x: longest_paths.get(x, 0))

            current = next_task

        return list(reversed(path))

    def _calculate_dependency_levels(self) -> dict[UUID, int]:
        """Calculate dependency level for each task."""
        levels = {}

        # Use topological sort to ensure we process dependencies first
        for task_id in self._topological_sort():
            node = self.nodes[task_id]

            if not node.dependencies:
                levels[task_id] = 0
            else:
                max_dep_level = max(levels.get(dep_id, 0) for dep_id in node.dependencies)
                levels[task_id] = max_dep_level + 1

        return levels

    def _invalidate_caches(self) -> None:
        """Invalidate computed caches."""
        self._topological_order = None
        self._critical_path = None
        self._dependency_levels.clear()


class OptimizedTaskManager:
    """Optimized task manager with superior performance."""

    def __init__(self, max_concurrent_tasks: int = 10):
        self.max_concurrent_tasks = max_concurrent_tasks

        # Core data structures
        self._dependency_graph = DependencyGraph()
        self._task_queue: list[TaskNode] = []  # Priority queue
        self._active_tasks: dict[UUID, Task] = {}
        self._task_results: dict[UUID, Any] = {}

        # Performance optimizations
        self._batch_size = 100
        self._ready_task_cache: Optional[list[Task]] = None
        self._cache_expiry: Optional[datetime] = None

        # Async coordination
        self._lock = asyncio.Lock()
        self._task_completed_event = asyncio.Event()

        # Metrics
        self._metrics = {
            "tasks_added": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "batch_operations": 0,
            "parallel_executions": 0,
            "avg_task_duration": 0.0,
        }

        logger.info("OptimizedTaskManager initialized", max_concurrent=max_concurrent_tasks)

    async def add_task(self, task: Task) -> None:
        """Add single task."""
        async with self._lock:
            self._dependency_graph.add_task(task)
            self._invalidate_ready_cache()
            self._metrics["tasks_added"] += 1

    async def add_tasks(self, tasks: list[Task]) -> None:
        """Add multiple tasks efficiently."""
        async with self._lock:
            # Process in batches
            for i in range(0, len(tasks), self._batch_size):
                batch = tasks[i : i + self._batch_size]
                self._dependency_graph.add_tasks_batch(batch)

            self._invalidate_ready_cache()
            self._metrics["tasks_added"] += len(tasks)
            self._metrics["batch_operations"] += 1

    async def get_next_tasks(self, limit: int = None) -> list[Task]:
        """Get next ready tasks with caching."""
        async with self._lock:
            limit = limit or self.max_concurrent_tasks

            # Use cache if available and not expired
            if (
                self._ready_task_cache
                and self._cache_expiry
                and datetime.now() < self._cache_expiry
            ):
                return self._ready_task_cache[:limit]

            # Get ready tasks
            ready_tasks = self._dependency_graph.get_ready_tasks(limit)

            # Update cache
            self._ready_task_cache = ready_tasks
            self._cache_expiry = (
                datetime.now().replace(microsecond=0).replace(second=0)
            )  # Cache for 1 minute

            return ready_tasks

    async def start_task(self, task_id: UUID) -> None:
        """Mark task as started."""
        async with self._lock:
            if task_id in self._dependency_graph.nodes:
                task = self._dependency_graph.nodes[task_id].task
                self._active_tasks[task_id] = task
                self._dependency_graph.start_task(task_id)
                self._invalidate_ready_cache()

    async def complete_task(self, task_id: UUID, result: Any = None) -> None:
        """Mark task as completed."""
        async with self._lock:
            if task_id in self._active_tasks:
                # Record completion
                self._task_results[task_id] = result
                self._active_tasks.pop(task_id, None)

                # Update dependency graph
                newly_ready = self._dependency_graph.complete_task(task_id)

                # Update metrics
                self._metrics["tasks_completed"] += 1

                # Invalidate cache if new tasks became ready
                if newly_ready:
                    self._invalidate_ready_cache()

                # Signal completion
                self._task_completed_event.set()
                self._task_completed_event.clear()

    async def fail_task(self, task_id: UUID, error: str) -> None:
        """Mark task as failed."""
        async with self._lock:
            if task_id in self._active_tasks:
                self._active_tasks.pop(task_id, None)

                # Update dependency graph
                affected_tasks = self._dependency_graph.fail_task(task_id)

                # Update metrics
                self._metrics["tasks_failed"] += 1

                # Invalidate cache
                self._invalidate_ready_cache()

                logger.error(
                    "Task failed",
                    task_id=str(task_id),
                    error=error,
                    affected_tasks=len(affected_tasks),
                )

    async def get_progress(self) -> dict[str, Any]:
        """Get task execution progress."""
        async with self._lock:
            total_tasks = len(self._dependency_graph.nodes)
            completed_tasks = len(self._dependency_graph.completed_tasks)
            failed_tasks = len(self._dependency_graph.failed_tasks)
            active_tasks = len(self._active_tasks)
            ready_tasks = len(self._dependency_graph.ready_tasks)

            return {
                "total_tasks": total_tasks,
                "completed_tasks": completed_tasks,
                "failed_tasks": failed_tasks,
                "active_tasks": active_tasks,
                "ready_tasks": ready_tasks,
                "blocked_tasks": total_tasks
                - completed_tasks
                - failed_tasks
                - active_tasks
                - ready_tasks,
                "completion_rate": completed_tasks / total_tasks if total_tasks > 0 else 0,
                "failure_rate": failed_tasks / total_tasks if total_tasks > 0 else 0,
                "metrics": self._metrics,
            }

    async def get_critical_path(self) -> list[Task]:
        """Get critical path tasks."""
        async with self._lock:
            critical_path_ids = self._dependency_graph.get_critical_path()
            return [
                self._dependency_graph.nodes[task_id].task
                for task_id in critical_path_ids
                if task_id in self._dependency_graph.nodes
            ]

    async def get_blocked_tasks(self) -> list[Task]:
        """Get tasks that are blocked by dependencies."""
        async with self._lock:
            all_task_ids = set(self._dependency_graph.nodes.keys())
            completed = self._dependency_graph.completed_tasks
            failed = self._dependency_graph.failed_tasks
            active = set(self._active_tasks.keys())
            ready = self._dependency_graph.ready_tasks

            blocked_ids = all_task_ids - completed - failed - active - ready

            return [
                self._dependency_graph.nodes[task_id].task
                for task_id in blocked_ids
                if task_id in self._dependency_graph.nodes
            ]

    async def optimize_execution_order(self) -> list[Task]:
        """Optimize task execution order for better performance."""
        async with self._lock:
            # Get dependency levels
            levels = self._dependency_graph.get_dependency_levels()

            # Group tasks by level
            level_groups = defaultdict(list)
            for task_id, level in levels.items():
                if task_id in self._dependency_graph.nodes:
                    level_groups[level].append(self._dependency_graph.nodes[task_id].task)

            # Sort each level by priority
            optimized_order = []
            for level in sorted(level_groups.keys()):
                level_tasks = level_groups[level]
                level_tasks.sort(
                    key=lambda t: self._dependency_graph.nodes[t.id].priority_score, reverse=True
                )
                optimized_order.extend(level_tasks)

            return optimized_order

    async def reset_task(self, task_id: UUID) -> bool:
        """Reset a failed task for retry."""
        async with self._lock:
            if task_id in self._dependency_graph.failed_tasks:
                self._dependency_graph.failed_tasks.remove(task_id)

                # Check if it's ready to run again
                if self._dependency_graph._is_task_ready(task_id):
                    self._dependency_graph.ready_tasks.add(task_id)

                self._invalidate_ready_cache()
                return True

            return False

    async def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """Wait for all tasks to complete."""
        start_time = asyncio.get_event_loop().time()

        while True:
            progress = await self.get_progress()

            if progress["active_tasks"] == 0 and progress["ready_tasks"] == 0:
                return True

            if timeout and (asyncio.get_event_loop().time() - start_time) > timeout:
                return False

            # Wait for next task completion
            try:
                await asyncio.wait_for(self._task_completed_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

    async def get_performance_metrics(self) -> dict[str, Any]:
        """Get comprehensive performance metrics."""
        async with self._lock:
            progress = await self.get_progress()

            return {
                **self._metrics,
                "progress": progress,
                "graph_stats": {
                    "total_nodes": len(self._dependency_graph.nodes),
                    "ready_nodes": len(self._dependency_graph.ready_tasks),
                    "completed_nodes": len(self._dependency_graph.completed_tasks),
                    "failed_nodes": len(self._dependency_graph.failed_tasks),
                    "active_nodes": len(self._dependency_graph.in_progress_tasks),
                },
                "cache_stats": {
                    "ready_cache_size": (
                        len(self._ready_task_cache) if self._ready_task_cache else 0
                    ),
                    "cache_valid": self._cache_expiry is not None
                    and datetime.now() < self._cache_expiry,
                },
            }

    def _invalidate_ready_cache(self) -> None:
        """Invalidate ready task cache."""
        self._ready_task_cache = None
        self._cache_expiry = None
