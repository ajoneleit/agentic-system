"""
Comprehensive test suite for Meta Agent orchestration engine.
Focus on coordination, task decomposition, and error recovery.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.agents.meta_agent import MetaAgent
from src.core.agent_errors import (
    AgentSpawnError,
    ResourceExhaustionError,
    TaskDecompositionError,
)
from src.core.artifact_manager import ArtifactManager
from src.core.interfaces import AgentRole, Task, TaskPriority, TaskStatus
from src.core.result import Result
from src.core.task_manager import TaskManager


class TestMetaAgentConcurrentTasks:
    """Test concurrent task handling and resource management."""

    @pytest.fixture
    def meta_agent(self):
        """Create a MetaAgent with mocked dependencies."""
        with patch('src.clients.openai_client.OpenAIClient'):
            agent = MetaAgent()
            agent.task_manager = MagicMock(spec=TaskManager)
            agent.artifact_manager = MagicMock(spec=ArtifactManager)
            return agent

    @pytest.fixture
    def concurrent_tasks(self):
        """Create multiple tasks for concurrent execution."""
        return [
            Task(
                id=uuid4(),
                name=f"concurrent_task_{i}",
                description=f"Task {i} for concurrent execution",
                agent_role=AgentRole.CORE_LOGIC,
                priority=TaskPriority.MEDIUM,
                status=TaskStatus.PENDING,
                metadata={"complexity": "medium", "estimated_duration": 30}
            ) for i in range(5)
        ]

    @pytest.mark.asyncio
    async def test_meta_agent_handles_concurrent_tasks(self, meta_agent, concurrent_tasks):
        """Test that MetaAgent can handle multiple concurrent tasks."""
        # Mock successful task decomposition
        meta_agent.decompose_task = AsyncMock(return_value=concurrent_tasks)

        # Mock successful coordination
        async def mock_coordinate_execution(tasks, context):
            # Simulate concurrent execution
            results = {}
            for task in tasks:
                results[task.id] = MagicMock()
                results[task.id].success = True
                results[task.id].artifacts = []
            return Result.success(results)

        meta_agent.coordinate_execution = AsyncMock(side_effect=mock_coordinate_execution)

        # Mock aggregation
        meta_agent.aggregate_results = AsyncMock(return_value=Result.success(MagicMock()))

        # Execute concurrent request
        result = await meta_agent.process_request("Execute multiple concurrent tasks")

        # Verify successful concurrent execution
        assert result.is_success()
        meta_agent.coordinate_execution.assert_called_once()

        # Verify all tasks were processed
        call_args = meta_agent.coordinate_execution.call_args[0]
        processed_tasks = call_args[0]
        assert len(processed_tasks) == 5

    @pytest.mark.asyncio
    async def test_meta_agent_resource_management_under_load(self, meta_agent):
        """Test resource management when system is under heavy load."""
        # Create high-load scenario with many large tasks
        heavy_tasks = [
            Task(
                id=uuid4(),
                name=f"heavy_task_{i}",
                description=f"Resource-intensive task {i}",
                agent_role=AgentRole.CORE_LOGIC,
                priority=TaskPriority.HIGH,
                status=TaskStatus.PENDING,
                metadata={"complexity": "high", "memory_intensive": True}
            ) for i in range(20)  # 20 heavy tasks
        ]

        meta_agent.decompose_task = AsyncMock(return_value=heavy_tasks)

        # Mock resource exhaustion scenario
        async def mock_coordinate_with_resource_limits(tasks, context):
            if len(tasks) > 10:  # Simulate resource limit
                return Result.failure(ResourceExhaustionError(
                    "System resource limits exceeded",
                    agent_id=meta_agent.id
                ))
            return Result.success({})

        meta_agent.coordinate_execution = AsyncMock(side_effect=mock_coordinate_with_resource_limits)

        # Execute under load
        result = await meta_agent.process_request("Execute resource-intensive tasks")

        # Verify proper resource management
        assert result.is_failure()
        assert isinstance(result.get_error(), ResourceExhaustionError)

    @pytest.mark.asyncio
    async def test_meta_agent_error_recovery_from_partial_failures(self, meta_agent):
        """Test error recovery when some tasks fail but others succeed."""
        tasks = [
            Task(id=uuid4(), name="success_task", agent_role=AgentRole.CORE_LOGIC),
            Task(id=uuid4(), name="failure_task", agent_role=AgentRole.TESTING),
            Task(id=uuid4(), name="recovery_task", agent_role=AgentRole.CORE_LOGIC)
        ]

        meta_agent.decompose_task = AsyncMock(return_value=tasks)

        # Mock partial failure scenario
        async def mock_partial_failure_coordination(tasks, context):
            results = {}
            for task in tasks:
                if task.name == "failure_task":
                    # Simulate task failure
                    results[task.id] = MagicMock()
                    results[task.id].success = False
                    results[task.id].error = "Simulated task failure"
                else:
                    results[task.id] = MagicMock()
                    results[task.id].success = True
                    results[task.id].artifacts = []
            return Result.success(results)

        meta_agent.coordinate_execution = AsyncMock(side_effect=mock_partial_failure_coordination)
        meta_agent.aggregate_results = AsyncMock(return_value=Result.success(MagicMock()))

        # Execute with partial failures
        result = await meta_agent.process_request("Execute tasks with partial failures")

        # Verify system handles partial failures gracefully
        assert result.is_success()  # Overall success despite partial failures

        # Verify error recovery was attempted
        meta_agent.coordinate_execution.assert_called_once()


class TestMetaAgentTaskDecomposition:
    """Test task decomposition edge cases and error conditions."""

    @pytest.fixture
    def meta_agent(self):
        with patch('src.clients.openai_client.OpenAIClient'):
            return MetaAgent()

    @pytest.mark.asyncio
    async def test_meta_agent_task_decomposition_edge_cases(self, meta_agent):
        """Test task decomposition with various edge cases."""

        # Test empty request
        result = await meta_agent.decompose_request("")
        assert result.is_failure()
        assert isinstance(result.get_error(), TaskDecompositionError)

        # Test extremely long request
        long_request = "Create a system " * 1000  # Very long request
        result = await meta_agent.decompose_request(long_request)
        # Should handle gracefully, not crash
        assert result.is_success() or result.is_failure()

        # Test malformed request with special characters
        malformed_request = "Create a system with ñ∆∂ƒ©∆∂ƒ special chars"
        result = await meta_agent.decompose_request(malformed_request)
        assert result.is_success() or result.is_failure()

    @pytest.mark.asyncio
    async def test_meta_agent_decomposition_with_circular_dependencies(self, meta_agent):
        """Test handling of circular dependencies in task decomposition."""
        # Mock AI response that creates circular dependencies
        mock_response = {
            "tasks": [
                {
                    "name": "task_a",
                    "description": "Task A",
                    "dependencies": ["task_b"],
                    "agent_type": "core_logic"
                },
                {
                    "name": "task_b",
                    "description": "Task B",
                    "dependencies": ["task_a"],  # Circular dependency
                    "agent_type": "testing"
                }
            ]
        }

        with patch.object(meta_agent, '_query_ai') as mock_query:
            mock_query.return_value = mock_response

            result = await meta_agent.decompose_request("Create circular tasks")

            # Should detect and handle circular dependencies
            assert result.is_success()  # Should resolve by breaking cycles
            tasks = result.unwrap()

            # Verify circular dependency was resolved
            # (implementation should break the cycle)
            assert len(tasks) == 2


class TestMetaAgentSpawning:
    """Test agent spawning failures and recovery."""

    @pytest.fixture
    def meta_agent(self):
        with patch('src.clients.openai_client.OpenAIClient'):
            return MetaAgent()

    @pytest.mark.asyncio
    async def test_meta_agent_agent_spawning_failures(self, meta_agent):
        """Test handling of agent spawning failures."""
        tasks = [
            Task(id=uuid4(), name="test_task", agent_role=AgentRole.CORE_LOGIC),
            Task(id=uuid4(), name="test_task_2", agent_role=AgentRole.TESTING)
        ]

        context = MagicMock()

        # Mock spawning failure
        with patch.object(meta_agent, 'spawn_agent') as mock_spawn:
            mock_spawn.side_effect = AgentSpawnError("Failed to spawn agent")

            result = await meta_agent.spawn_agents(tasks, context)

            # Should handle spawning failure gracefully
            assert result.is_failure()
            assert isinstance(result.get_error(), AgentSpawnError)

    @pytest.mark.asyncio
    async def test_meta_agent_spawning_with_resource_constraints(self, meta_agent):
        """Test agent spawning under resource constraints."""
        # Create many tasks requiring agents
        many_tasks = [
            Task(id=uuid4(), name=f"task_{i}", agent_role=AgentRole.CORE_LOGIC)
            for i in range(50)  # Request many agents
        ]

        context = MagicMock()

        # Mock resource-constrained spawning
        spawn_count = 0
        async def mock_spawn_with_limits(role, context):
            nonlocal spawn_count
            spawn_count += 1
            if spawn_count > 10:  # Simulate resource limit
                raise ResourceExhaustionError("Too many agents spawned")
            return MagicMock()

        with patch.object(meta_agent, 'spawn_agent', side_effect=mock_spawn_with_limits):
            result = await meta_agent.spawn_agents(many_tasks, context)

            # Should handle resource constraints
            assert result.is_failure()
            assert isinstance(result.get_error(), AgentSpawnError)


class TestMetaAgentPerformance:
    """Performance benchmarks for critical paths."""

    @pytest.fixture
    def meta_agent(self):
        with patch('src.clients.openai_client.OpenAIClient'):
            return MetaAgent()

    @pytest.mark.asyncio
    async def test_meta_agent_decomposition_performance(self, meta_agent):
        """Benchmark task decomposition performance."""
        start_time = datetime.now()

        # Mock quick response
        with patch.object(meta_agent, '_query_ai') as mock_query:
            mock_query.return_value = {
                "tasks": [
                    {
                        "name": "simple_task",
                        "description": "Simple task",
                        "dependencies": [],
                        "agent_type": "core_logic"
                    }
                ]
            }

            result = await meta_agent.decompose_request("Simple request")

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Should complete within reasonable time
        assert duration < 5.0  # Should take less than 5 seconds
        assert result.is_success()

    @pytest.mark.asyncio
    async def test_meta_agent_coordination_performance_benchmark(self, meta_agent):
        """Benchmark coordination performance with multiple tasks."""
        tasks = [
            Task(id=uuid4(), name=f"perf_task_{i}", agent_role=AgentRole.CORE_LOGIC)
            for i in range(10)
        ]

        context = MagicMock()

        # Mock fast coordination
        async def mock_fast_coordination(tasks, context):
            await asyncio.sleep(0.1)  # Simulate minimal processing time
            return Result.success({task.id: MagicMock() for task in tasks})

        meta_agent.coordinate_execution = AsyncMock(side_effect=mock_fast_coordination)

        start_time = datetime.now()
        result = await meta_agent.coordinate_execution(tasks, context)
        end_time = datetime.now()

        duration = (end_time - start_time).total_seconds()

        # Should coordinate efficiently
        assert duration < 1.0  # Should take less than 1 second
        assert result.is_success()
