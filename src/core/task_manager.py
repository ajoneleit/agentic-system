"""Task management system for the Agentic Coding System.

This module handles task queuing, dependency resolution, and execution orchestration
with support for parallel execution and priority-based scheduling.
"""

import asyncio
import heapq
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional, Tuple, Any
from uuid import UUID
import networkx as nx

from structlog import get_logger

from src.core.exceptions import (
    TaskDependencyError,
    TaskError,
)
from src.core.interfaces import (
    Task,
    TaskStatus,
    TaskPriority,
)


logger = get_logger(__name__)


class TaskQueue:
    """Priority-based task queue with dependency awareness."""
    
    def __init__(self):
        """Initialize task queue."""
        self._heap: List[Tuple[int, datetime, Task]] = []
        self._task_map: Dict[UUID, Task] = {}
        self._counter = 0
        self._lock = asyncio.Lock()
    
    async def add_task(self, task: Task) -> None:
        """Add a task to the queue.
        
        Args:
            task: Task to add
        """
        async with self._lock:
            priority_value = self._get_priority_value(task.priority)
            self._counter += 1
            
            heapq.heappush(
                self._heap,
                (priority_value, task.created_at, task)
            )
            self._task_map[task.id] = task
            
            logger.debug(
                "Task added to queue",
                task_id=str(task.id),
                task_name=task.name,
                priority=task.priority.value,
            )
    
    async def get_next_ready_task(
        self,
        completed_tasks: Set[UUID]
    ) -> Optional[Task]:
        """Get the next task that's ready to execute.
        
        Args:
            completed_tasks: Set of completed task IDs
            
        Returns:
            Next ready task or None
        """
        async with self._lock:
            temp_heap = []
            
            while self._heap:
                priority, created_at, task = heapq.heappop(self._heap)
                
                if task.status != TaskStatus.PENDING:
                    continue
                
                if task.is_ready(completed_tasks):
                    # Put back any tasks we removed
                    for item in temp_heap:
                        heapq.heappush(self._heap, item)
                    
                    return task
                else:
                    temp_heap.append((priority, created_at, task))
            
            # Put back all tasks
            for item in temp_heap:
                heapq.heappush(self._heap, item)
            
            return None
    
    async def remove_task(self, task_id: UUID) -> Optional[Task]:
        """Remove a task from the queue.
        
        Args:
            task_id: ID of task to remove
            
        Returns:
            Removed task or None
        """
        async with self._lock:
            if task_id not in self._task_map:
                return None
            
            task = self._task_map.pop(task_id)
            
            # Rebuild heap without the removed task
            self._heap = [
                (p, c, t) for p, c, t in self._heap
                if t.id != task_id
            ]
            heapq.heapify(self._heap)
            
            return task
    
    async def get_all_tasks(self) -> List[Task]:
        """Get all tasks in the queue.
        
        Returns:
            List of all tasks
        """
        async with self._lock:
            return list(self._task_map.values())
    
    async def get_task(self, task_id: UUID) -> Optional[Task]:
        """Get a specific task.
        
        Args:
            task_id: ID of task to get
            
        Returns:
            Task or None
        """
        async with self._lock:
            return self._task_map.get(task_id)
    
    async def update_task(self, task: Task) -> None:
        """Update a task in the queue.
        
        Args:
            task: Updated task
        """
        async with self._lock:
            if task.id in self._task_map:
                self._task_map[task.id] = task
                
                # Rebuild heap with updated task
                self._heap = [
                    (self._get_priority_value(t.priority), t.created_at, t)
                    if t.id != task.id
                    else (self._get_priority_value(task.priority), task.created_at, task)
                    for _, _, t in self._heap
                ]
                heapq.heapify(self._heap)
    
    def _get_priority_value(self, priority: TaskPriority) -> int:
        """Convert priority to numeric value for heap.
        
        Args:
            priority: Task priority
            
        Returns:
            Numeric priority (lower is higher priority)
        """
        priority_map = {
            TaskPriority.CRITICAL: 0,
            TaskPriority.HIGH: 1,
            TaskPriority.MEDIUM: 2,
            TaskPriority.LOW: 3,
        }
        return priority_map[priority]
    
    async def size(self) -> int:
        """Get number of tasks in queue.
        
        Returns:
            Queue size
        """
        async with self._lock:
            return len(self._task_map)


class DependencyResolver:
    """Resolves task dependencies and detects cycles."""
    
    def __init__(self):
        """Initialize dependency resolver."""
        self._graph = nx.DiGraph()
        self._lock = asyncio.Lock()
    
    async def add_tasks(self, tasks: List[Task]) -> None:
        """Add tasks and their dependencies to the graph.
        
        Args:
            tasks: List of tasks to add
            
        Raises:
            TaskDependencyError: If circular dependencies detected
        """
        async with self._lock:
            # Add all tasks as nodes first
            for task in tasks:
                self._graph.add_node(
                    task.id,
                    task=task,
                    name=task.name
                )
            
            # Add dependency edges
            for task in tasks:
                for dep_id in task.dependencies:
                    if dep_id in self._graph:
                        self._graph.add_edge(dep_id, task.id)
            
            # Check for cycles
            if not nx.is_directed_acyclic_graph(self._graph):
                cycles = list(nx.simple_cycles(self._graph))
                raise TaskDependencyError(
                    task_id=tasks[0].id,
                    missing_deps=cycles[0] if cycles else []
                )
    
    async def get_execution_order(self) -> List[List[UUID]]:
        """Get tasks grouped by execution phase.
        
        Returns:
            List of task ID groups that can execute in parallel
        """
        async with self._lock:
            if not self._graph:
                return []
            
            # Topological generations give us parallel execution groups
            try:
                generations = list(nx.topological_generations(self._graph))
                return [[node for node in gen] for gen in generations]
            except nx.NetworkXError as e:
                logger.error("Failed to determine execution order", error=str(e))
                return []
    
    async def get_dependencies(self, task_id: UUID) -> Set[UUID]:
        """Get all dependencies for a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            Set of dependency task IDs
        """
        async with self._lock:
            if task_id not in self._graph:
                return set()
            
            return set(self._graph.predecessors(task_id))
    
    async def get_dependents(self, task_id: UUID) -> Set[UUID]:
        """Get all tasks that depend on this task.
        
        Args:
            task_id: Task ID
            
        Returns:
            Set of dependent task IDs
        """
        async with self._lock:
            if task_id not in self._graph:
                return set()
            
            return set(self._graph.successors(task_id))
    
    async def remove_task(self, task_id: UUID) -> None:
        """Remove a task from the dependency graph.
        
        Args:
            task_id: Task ID to remove
        """
        async with self._lock:
            if task_id in self._graph:
                self._graph.remove_node(task_id)
    
    async def get_critical_path(self) -> List[UUID]:
        """Get the critical path through the task graph.
        
        Returns:
            List of task IDs forming the critical path
        """
        async with self._lock:
            if not self._graph:
                return []
            
            # Find all paths from roots to leaves
            roots = [n for n in self._graph.nodes() if self._graph.in_degree(n) == 0]
            leaves = [n for n in self._graph.nodes() if self._graph.out_degree(n) == 0]
            
            longest_path = []
            max_length = 0
            
            for root in roots:
                for leaf in leaves:
                    try:
                        paths = list(nx.all_simple_paths(self._graph, root, leaf))
                        for path in paths:
                            if len(path) > max_length:
                                max_length = len(path)
                                longest_path = path
                    except nx.NetworkXNoPath:
                        continue
            
            return longest_path


class TaskManager:
    """Manages task execution, dependencies, and scheduling."""
    
    def __init__(self, max_parallel_tasks: int = 10):
        """Initialize task manager.
        
        Args:
            max_parallel_tasks: Maximum tasks to execute in parallel
        """
        self.max_parallel_tasks = max_parallel_tasks
        self._queue = TaskQueue()
        self._resolver = DependencyResolver()
        self._active_tasks: Dict[UUID, Task] = {}
        self._completed_tasks: Set[UUID] = set()
        self._failed_tasks: Dict[UUID, str] = {}
        self._task_futures: Dict[UUID, asyncio.Future] = {}
        self._lock = asyncio.Lock()
        
        logger.info(
            "Task manager initialized",
            max_parallel_tasks=max_parallel_tasks,
        )
    
    async def add_tasks(self, tasks: List[Task]) -> None:
        """Add multiple tasks to the system.
        
        Args:
            tasks: List of tasks to add
            
        Raises:
            TaskDependencyError: If circular dependencies detected
        """
        # Add to dependency resolver first to check for cycles
        await self._resolver.add_tasks(tasks)
        
        # Add to queue
        for task in tasks:
            await self._queue.add_task(task)
        
        logger.info(
            "Tasks added to manager",
            count=len(tasks),
            task_names=[t.name for t in tasks],
        )
    
    async def get_next_tasks(self, max_count: Optional[int] = None) -> List[Task]:
        """Get next tasks ready for execution.
        
        Args:
            max_count: Maximum number of tasks to return
            
        Returns:
            List of ready tasks
        """
        if max_count is None:
            max_count = self.max_parallel_tasks - len(self._active_tasks)
        
        ready_tasks = []
        
        for _ in range(max_count):
            task = await self._queue.get_next_ready_task(self._completed_tasks)
            if task:
                ready_tasks.append(task)
                async with self._lock:
                    self._active_tasks[task.id] = task
            else:
                break
        
        return ready_tasks
    
    async def start_task(self, task_id: UUID) -> None:
        """Mark a task as started.
        
        Args:
            task_id: ID of task to start
        """
        task = await self._queue.get_task(task_id)
        if task:
            task.mark_started()
            await self._queue.update_task(task)
            
            async with self._lock:
                self._active_tasks[task_id] = task
            
            logger.info(
                "Task started",
                task_id=str(task_id),
                task_name=task.name,
            )
    
    async def complete_task(
        self,
        task_id: UUID,
        artifacts: Optional[List[UUID]] = None
    ) -> None:
        """Mark a task as completed.
        
        Args:
            task_id: ID of task to complete
            artifacts: List of produced artifact IDs
        """
        async with self._lock:
            # Check if task is in active tasks
            if task_id in self._active_tasks:
                task = self._active_tasks.pop(task_id)
            else:
                # Try to get task from queue (might be pending)
                task = await self._queue.get_task(task_id)
                if not task:
                    logger.warning(
                        "Attempted to complete non-existent task",
                        task_id=str(task_id),
                    )
                    return
            
            task.mark_completed()
            
            if artifacts:
                task.artifacts.extend(artifacts)
            
            await self._queue.update_task(task)
            self._completed_tasks.add(task_id)
            
            # Resolve future if exists
            if task_id in self._task_futures:
                self._task_futures[task_id].set_result(task)
            
            logger.info(
                "Task completed",
                task_id=str(task_id),
                task_name=task.name,
                artifacts=len(artifacts) if artifacts else 0,
            )
    
    async def fail_task(self, task_id: UUID, error: str) -> None:
        """Mark a task as failed.
        
        Args:
            task_id: ID of task that failed
            error: Error message
        """
        async with self._lock:
            # Check if task is in active tasks
            if task_id in self._active_tasks:
                task = self._active_tasks.pop(task_id)
            else:
                # Try to get task from queue (might be pending)
                task = await self._queue.get_task(task_id)
                if not task:
                    logger.warning(
                        "Attempted to fail non-existent task",
                        task_id=str(task_id),
                    )
                    return
            
            task.mark_failed(error)
            await self._queue.update_task(task)
            self._failed_tasks[task_id] = error
            
            # Resolve future with exception
            if task_id in self._task_futures:
                self._task_futures[task_id].set_exception(
                        TaskError(task_id, f"Task failed: {error}")
                    )
                
                logger.error(
                    "Task failed",
                    task_id=str(task_id),
                    task_name=task.name,
                    error=error,
                )
    
    async def get_task_status(self, task_id: UUID) -> Optional[TaskStatus]:
        """Get the status of a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            Task status or None
        """
        task = await self._queue.get_task(task_id)
        return task.status if task else None
    
    async def get_progress(self) -> Dict[str, Any]:
        """Get overall progress information.
        
        Returns:
            Progress statistics
        """
        all_tasks = await self._queue.get_all_tasks()
        
        status_counts = defaultdict(int)
        for task in all_tasks:
            status_counts[task.status.value] += 1
        
        total = len(all_tasks)
        completed = len(self._completed_tasks)
        
        return {
            "total_tasks": total,
            "completed_tasks": completed,
            "active_tasks": len(self._active_tasks),
            "failed_tasks": len(self._failed_tasks),
            "pending_tasks": status_counts[TaskStatus.PENDING.value],
            "completion_percentage": (completed / total * 100) if total > 0 else 0,
            "status_breakdown": dict(status_counts),
        }
    
    async def get_blocked_tasks(self) -> List[Task]:
        """Get tasks that are blocked by dependencies.
        
        Returns:
            List of blocked tasks
        """
        all_tasks = await self._queue.get_all_tasks()
        blocked = []
        
        for task in all_tasks:
            if task.status == TaskStatus.PENDING:
                if not task.is_ready(self._completed_tasks):
                    blocked.append(task)
        
        return blocked
    
    async def get_critical_path(self) -> List[Task]:
        """Get tasks on the critical path.
        
        Returns:
            List of tasks forming the critical path
        """
        critical_ids = await self._resolver.get_critical_path()
        tasks = []
        
        for task_id in critical_ids:
            task = await self._queue.get_task(task_id)
            if task:
                tasks.append(task)
        
        return tasks
    
    async def wait_for_task(self, task_id: UUID) -> Task:
        """Wait for a task to complete.
        
        Args:
            task_id: Task ID to wait for
            
        Returns:
            Completed task
            
        Raises:
            TaskError: If task fails
        """
        if task_id in self._completed_tasks:
            task = await self._queue.get_task(task_id)
            if task:
                return task
        
        if task_id not in self._task_futures:
            self._task_futures[task_id] = asyncio.Future()
        
        return await self._task_futures[task_id]
    
    async def cancel_task(self, task_id: UUID) -> bool:
        """Cancel a pending or active task.
        
        Args:
            task_id: Task ID to cancel
            
        Returns:
            True if cancelled successfully
        """
        task = await self._queue.get_task(task_id)
        if not task:
            return False
        
        if task.status in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS]:
            task.status = TaskStatus.CANCELLED
            await self._queue.update_task(task)
            
            async with self._lock:
                if task_id in self._active_tasks:
                    del self._active_tasks[task_id]
            
            logger.info(
                "Task cancelled",
                task_id=str(task_id),
                task_name=task.name,
            )
            return True
        
        return False
    
    async def get_execution_plan(self) -> List[Dict[str, Any]]:
        """Get the planned execution order.
        
        Returns:
            Execution plan with parallel groups
        """
        phases = await self._resolver.get_execution_order()
        plan = []
        
        for i, phase_ids in enumerate(phases):
            tasks = []
            for task_id in phase_ids:
                task = await self._queue.get_task(task_id)
                if task:
                    tasks.append({
                        "id": str(task.id),
                        "name": task.name,
                        "status": task.status.value,
                        "priority": task.priority.value,
                    })
            
            plan.append({
                "phase": i + 1,
                "parallel_tasks": tasks,
                "can_parallel": True,
            })
        
        return plan