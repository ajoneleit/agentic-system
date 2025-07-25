"""Tests for the task management system."""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Add parent directory to path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.core.exceptions import TaskDependencyError
from src.core.interfaces import Task, TaskPriority, TaskStatus
from src.core.task_manager import (
    DependencyResolver,
    TaskManager,
    TaskQueue,
)


class TestTaskQueue:
    """Test TaskQueue functionality."""

    @pytest.mark.asyncio
    async def test_add_task(self):
        """Test adding tasks to queue."""
        queue = TaskQueue()

        task1 = Task(name="Task 1", description="First task", priority=TaskPriority.HIGH)
        task2 = Task(name="Task 2", description="Second task", priority=TaskPriority.LOW)

        await queue.add_task(task1)
        await queue.add_task(task2)

        assert await queue.size() == 2

    @pytest.mark.asyncio
    async def test_get_next_ready_task_priority(self):
        """Test getting tasks respects priority."""
        queue = TaskQueue()

        # Add tasks with different priorities
        low_task = Task(name="Low", description="Low priority", priority=TaskPriority.LOW)
        high_task = Task(name="High", description="High priority", priority=TaskPriority.HIGH)
        critical_task = Task(name="Critical", description="Critical priority", priority=TaskPriority.CRITICAL)

        await queue.add_task(low_task)
        await queue.add_task(high_task)
        await queue.add_task(critical_task)

        # Should get critical task first
        next_task = await queue.get_next_ready_task(set())
        assert next_task == critical_task

        # Mark as in progress and get next
        critical_task.status = TaskStatus.IN_PROGRESS
        await queue.update_task(critical_task)

        next_task = await queue.get_next_ready_task(set())
        assert next_task == high_task

    @pytest.mark.asyncio
    async def test_get_next_ready_task_dependencies(self):
        """Test getting tasks respects dependencies."""
        queue = TaskQueue()

        task1 = Task(name="Task 1", description="First task")
        task2 = Task(name="Task 2", description="Depends on 1", dependencies=[task1.id])
        task3 = Task(name="Task 3", description="Independent")

        await queue.add_task(task1)
        await queue.add_task(task2)
        await queue.add_task(task3)

        # Should get task1 or task3 (both ready)
        completed = set()
        next_task = await queue.get_next_ready_task(completed)
        assert next_task in [task1, task3]

        # Complete task1
        completed.add(task1.id)
        task1.status = TaskStatus.COMPLETED
        await queue.update_task(task1)

        # Now task2 should be ready
        task3.status = TaskStatus.IN_PROGRESS
        await queue.update_task(task3)

        next_task = await queue.get_next_ready_task(completed)
        assert next_task == task2

    @pytest.mark.asyncio
    async def test_remove_task(self):
        """Test removing tasks from queue."""
        queue = TaskQueue()

        task = Task(name="Task", description="Test task")
        await queue.add_task(task)

        assert await queue.size() == 1

        removed = await queue.remove_task(task.id)
        assert removed == task
        assert await queue.size() == 0

        # Try removing non-existent task
        removed = await queue.remove_task(uuid4())
        assert removed is None

    @pytest.mark.asyncio
    async def test_update_task(self):
        """Test updating tasks in queue."""
        queue = TaskQueue()

        task = Task(name="Task", description="Test task", priority=TaskPriority.LOW)
        await queue.add_task(task)

        # Update priority
        task.priority = TaskPriority.HIGH
        await queue.update_task(task)

        # Should reflect new priority
        next_task = await queue.get_next_ready_task(set())
        assert next_task.priority == TaskPriority.HIGH


class TestDependencyResolver:
    """Test DependencyResolver functionality."""

    @pytest.mark.asyncio
    async def test_add_tasks_no_cycles(self):
        """Test adding tasks without circular dependencies."""
        resolver = DependencyResolver()

        task1 = Task(name="Task 1", description="First")
        task2 = Task(name="Task 2", description="Second", dependencies=[task1.id])
        task3 = Task(name="Task 3", description="Third", dependencies=[task2.id])

        await resolver.add_tasks([task1, task2, task3])

        # Should succeed without errors
        assert True

    @pytest.mark.asyncio
    async def test_add_tasks_with_cycle(self):
        """Test detecting circular dependencies."""
        resolver = DependencyResolver()

        task1 = Task(name="Task 1", description="First")
        task2 = Task(name="Task 2", description="Second", dependencies=[task1.id])
        task3 = Task(name="Task 3", description="Third", dependencies=[task2.id])

        # Create cycle: task1 depends on task3
        task1.dependencies = [task3.id]

        with pytest.raises(TaskDependencyError):
            await resolver.add_tasks([task1, task2, task3])

    @pytest.mark.asyncio
    async def test_get_execution_order(self):
        """Test getting parallel execution groups."""
        resolver = DependencyResolver()

        # Create task graph:
        # task1 -> task3
        # task2 -> task3 -> task4
        task1 = Task(name="Task 1", description="First")
        task2 = Task(name="Task 2", description="Second")
        task3 = Task(name="Task 3", description="Third", dependencies=[task1.id, task2.id])
        task4 = Task(name="Task 4", description="Fourth", dependencies=[task3.id])

        await resolver.add_tasks([task1, task2, task3, task4])

        execution_order = await resolver.get_execution_order()

        # Should have 3 phases
        assert len(execution_order) == 3

        # Phase 1: task1 and task2 (can run in parallel)
        assert set(execution_order[0]) == {task1.id, task2.id}

        # Phase 2: task3
        assert execution_order[1] == [task3.id]

        # Phase 3: task4
        assert execution_order[2] == [task4.id]

    @pytest.mark.asyncio
    async def test_get_dependencies(self):
        """Test getting task dependencies."""
        resolver = DependencyResolver()

        task1 = Task(name="Task 1", description="First")
        task2 = Task(name="Task 2", description="Second")
        task3 = Task(name="Task 3", description="Third", dependencies=[task1.id, task2.id])

        await resolver.add_tasks([task1, task2, task3])

        deps = await resolver.get_dependencies(task3.id)
        assert deps == {task1.id, task2.id}

        deps = await resolver.get_dependencies(task1.id)
        assert deps == set()

    @pytest.mark.asyncio
    async def test_get_dependents(self):
        """Test getting tasks that depend on a task."""
        resolver = DependencyResolver()

        task1 = Task(name="Task 1", description="First")
        task2 = Task(name="Task 2", description="Second", dependencies=[task1.id])
        task3 = Task(name="Task 3", description="Third", dependencies=[task1.id])

        await resolver.add_tasks([task1, task2, task3])

        dependents = await resolver.get_dependents(task1.id)
        assert dependents == {task2.id, task3.id}

    @pytest.mark.asyncio
    async def test_get_critical_path(self):
        """Test finding critical path."""
        resolver = DependencyResolver()

        # Create linear dependency chain
        task1 = Task(name="Task 1", description="First")
        task2 = Task(name="Task 2", description="Second", dependencies=[task1.id])
        task3 = Task(name="Task 3", description="Third", dependencies=[task2.id])
        task4 = Task(name="Task 4", description="Fourth", dependencies=[task3.id])

        # Add parallel branch
        task5 = Task(name="Task 5", description="Fifth", dependencies=[task1.id])

        await resolver.add_tasks([task1, task2, task3, task4, task5])

        critical_path = await resolver.get_critical_path()

        # Critical path should be the longest: task1 -> task2 -> task3 -> task4
        assert critical_path == [task1.id, task2.id, task3.id, task4.id]


class TestTaskManager:
    """Test TaskManager functionality."""

    @pytest.fixture
    def task_manager(self):
        """Create TaskManager instance."""
        return TaskManager(max_parallel_tasks=3)

    @pytest.mark.asyncio
    async def test_add_tasks(self, task_manager):
        """Test adding tasks to manager."""
        task1 = Task(name="Task 1", description="First")
        task2 = Task(name="Task 2", description="Second")

        await task_manager.add_tasks([task1, task2])

        progress = await task_manager.get_progress()
        assert progress["total_tasks"] == 2
        assert progress["pending_tasks"] == 2

    @pytest.mark.asyncio
    async def test_get_next_tasks_respects_limit(self, task_manager):
        """Test getting tasks respects parallel limit."""
        tasks = [
            Task(name=f"Task {i}", description=f"Task {i}")
            for i in range(5)
        ]

        await task_manager.add_tasks(tasks)

        # Get first batch (should get max_parallel_tasks = 3)
        next_tasks = await task_manager.get_next_tasks()
        assert len(next_tasks) == 3  # max_parallel_tasks

        # All 3 tasks should now be in active_tasks
        assert len(task_manager._active_tasks) == 3

        # Should get 0 more since we're at the limit
        next_tasks = await task_manager.get_next_tasks()
        assert len(next_tasks) == 0

        # Complete one task to free up a slot
        await task_manager.complete_task(tasks[0].id)

        # Now should get 1 more
        next_tasks = await task_manager.get_next_tasks()
        assert len(next_tasks) == 1

    @pytest.mark.asyncio
    async def test_task_lifecycle(self, task_manager):
        """Test complete task lifecycle."""
        task = Task(name="Task", description="Test task")
        await task_manager.add_tasks([task])

        # Start task
        await task_manager.start_task(task.id)
        status = await task_manager.get_task_status(task.id)
        assert status == TaskStatus.IN_PROGRESS

        # Complete task
        artifact_ids = [uuid4(), uuid4()]
        await task_manager.complete_task(task.id, artifact_ids)

        status = await task_manager.get_task_status(task.id)
        assert status == TaskStatus.COMPLETED

        progress = await task_manager.get_progress()
        assert progress["completed_tasks"] == 1
        assert task.id in task_manager._completed_tasks

    @pytest.mark.asyncio
    async def test_fail_task(self, task_manager):
        """Test failing a task."""
        task = Task(name="Task", description="Test task")
        await task_manager.add_tasks([task])

        # Get and fail task
        next_tasks = await task_manager.get_next_tasks()
        await task_manager.fail_task(task.id, "Test error")

        status = await task_manager.get_task_status(task.id)
        assert status == TaskStatus.FAILED

        progress = await task_manager.get_progress()
        assert progress["failed_tasks"] == 1
        assert task_manager._failed_tasks[task.id] == "Test error"

    @pytest.mark.asyncio
    async def test_get_blocked_tasks(self, task_manager):
        """Test identifying blocked tasks."""
        task1 = Task(name="Task 1", description="First")
        task2 = Task(name="Task 2", description="Depends on 1", dependencies=[task1.id])
        task3 = Task(name="Task 3", description="Depends on 2", dependencies=[task2.id])

        await task_manager.add_tasks([task1, task2, task3])

        blocked = await task_manager.get_blocked_tasks()
        # task2 and task3 are blocked
        assert len(blocked) == 2
        assert all(t.id in [task2.id, task3.id] for t in blocked)

        # Start and complete task1
        await task_manager.start_task(task1.id)
        await task_manager.complete_task(task1.id)

        blocked = await task_manager.get_blocked_tasks()
        # Only task3 is blocked now
        assert len(blocked) == 1
        assert blocked[0].id == task3.id

    @pytest.mark.asyncio
    async def test_wait_for_task(self, task_manager):
        """Test waiting for task completion."""
        task = Task(name="Task", description="Test task")
        await task_manager.add_tasks([task])

        # Start the task
        await task_manager.start_task(task.id)

        # Start async wait
        wait_task = asyncio.create_task(task_manager.wait_for_task(task.id))

        # Complete task after delay
        await asyncio.sleep(0.1)
        await task_manager.complete_task(task.id)

        # Wait should complete
        result = await wait_task
        assert result.id == task.id
        assert result.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_cancel_task(self, task_manager):
        """Test cancelling a task."""
        task = Task(name="Task", description="Test task")
        await task_manager.add_tasks([task])

        # Cancel pending task
        success = await task_manager.cancel_task(task.id)
        assert success

        status = await task_manager.get_task_status(task.id)
        assert status == TaskStatus.CANCELLED

        # Try to cancel completed task
        completed_task = Task(name="Completed", description="Already done")
        completed_task.status = TaskStatus.COMPLETED
        await task_manager.add_tasks([completed_task])

        success = await task_manager.cancel_task(completed_task.id)
        assert not success

    @pytest.mark.asyncio
    async def test_get_execution_plan(self, task_manager):
        """Test getting execution plan."""
        # Create tasks with dependencies
        task1 = Task(name="Setup", description="Setup environment")
        task2 = Task(name="Build", description="Build project", dependencies=[task1.id])
        task3 = Task(name="Test", description="Run tests", dependencies=[task2.id])
        task4 = Task(name="Docs", description="Generate docs", dependencies=[task1.id])

        await task_manager.add_tasks([task1, task2, task3, task4])

        plan = await task_manager.get_execution_plan()

        # Should have 3 phases
        assert len(plan) == 3

        # Phase 1: Setup
        assert plan[0]["phase"] == 1
        assert len(plan[0]["parallel_tasks"]) == 1
        assert plan[0]["parallel_tasks"][0]["name"] == "Setup"

        # Phase 2: Build and Docs (parallel)
        assert plan[1]["phase"] == 2
        assert len(plan[1]["parallel_tasks"]) == 2
        task_names = {t["name"] for t in plan[1]["parallel_tasks"]}
        assert task_names == {"Build", "Docs"}

        # Phase 3: Test
        assert plan[2]["phase"] == 3
        assert plan[2]["parallel_tasks"][0]["name"] == "Test"
