"""Tests for error handling and edge cases."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.agents import MetaAgent, CodeGeneratorAgent
from src.core.exceptions import (
    AgentError,
    TaskExecutionError,
)
from src.core.interfaces import (
    AgentRole,
    Task,
    TaskContext,
    TaskPriority,
    TaskStatus,
)


class TestErrorHandling:
    """Test error handling throughout the system."""
    
    
    @pytest.mark.asyncio
    async def test_sub_agent_task_execution_failure(self):
        """Test SubAgent handling of task execution failures."""
        agent = CodeGeneratorAgent(uuid4())
        
        context = TaskContext(
            project_root=Path("/tmp/test"),
            shared_memory={"test": True}
        )
        
        task = Task(
            name="Failing Task",
            description="This will fail",
            priority=TaskPriority.HIGH,
        )
        
        with patch('src.agents.sub_agent.ClaudeClient'), \
             patch('src.agents.sub_agent.ClaudeCodeClient') as mock_cli:
            # Mock CLI as not available to force API usage
            mock_cli_instance = mock_cli.return_value
            mock_cli_instance.check_cli_available = AsyncMock(return_value=False)
            mock_cli_instance.close = AsyncMock()
            
            await agent.initialize(context)
            
            # Mock Claude Code client to simulate a failure
            agent.claude_code_client.create_message_for_code = AsyncMock(
                side_effect=Exception("Simulated CLI failure")
            )
            
            # Execute task - should return failed result
            result = await agent.execute_task(task, context)
            
            assert not result.success
            assert len(result.errors) > 0
            assert "Claude Code query failed" in result.errors[0]
            assert task.id not in agent.completed_tasks  # Failed tasks are not added to completed_tasks
    
    
    @pytest.mark.asyncio
    async def test_agent_initialization_failure(self):
        """Test agent initialization failure handling."""
        context = TaskContext(
            project_root=Path("/tmp/test"),
            shared_memory={}
        )
        
        with patch('src.agents.sub_agent.ClaudeCodeClient') as mock_cli:
            # Mock CLI as not available to simulate initialization failure
            mock_cli_instance = mock_cli.return_value
            mock_cli_instance.check_cli_available = AsyncMock(return_value=False)
            mock_cli_instance.close = AsyncMock()
            
            agent = CodeGeneratorAgent(uuid4())
            
            # The initialization should fail when CLI is not available
            result = await agent.initialize(context)
            
            assert not result.is_success()
            assert "Claude Code is required" in str(result.get_error())
    
    
    @pytest.mark.asyncio
    async def test_task_timeout_handling(self):
        """Test handling of task timeouts."""
        agent = CodeGeneratorAgent(uuid4())
        
        context = TaskContext(
            project_root=Path("/tmp/test"),
            shared_memory={},
            global_constraints={"max_execution_time": 0.1}  # 100ms timeout
        )
        
        task = Task(
            name="Slow Task",
            description="This will timeout",
        )
        
        with patch('src.agents.sub_agent.ClaudeClient'), \
             patch('src.agents.sub_agent.ClaudeCodeClient') as mock_cli:
            # Mock CLI as not available to force API usage
            mock_cli_instance = mock_cli.return_value
            mock_cli_instance.check_cli_available = AsyncMock(return_value=False)
            mock_cli_instance.close = AsyncMock()
            
            await agent.initialize(context)
            
            # Mock Claude to simulate slow response
            async def slow_response(*args, **kwargs):
                await asyncio.sleep(0.5)  # Longer than timeout
                return MagicMock()
            
            agent.claude_client.create_message = slow_response
            
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(
                    agent.execute_task(task, context),
                    timeout=0.2
                )
    
    
    @pytest.mark.asyncio
    async def test_concurrent_task_failure_handling(self):
        """Test handling of multiple concurrent task failures."""
        with patch('src.agents.meta_agent.ClaudeClient'), \
             patch('src.agents.meta_agent.TaskManager'), \
             patch('src.agents.meta_agent.CommunicationHub'), \
             patch('src.agents.meta_agent.AgentCoordinator'):
            
            meta_agent = MetaAgent()
            meta_agent.context = TaskContext(
                project_root=Path("/tmp/test"),
                shared_memory={}
            )
            # Mock coordinator.start method
            meta_agent.coordinator.start = AsyncMock()
            
            # Create multiple tasks
            tasks = [
                Task(name=f"Task {i}", description=f"Task {i}") 
                for i in range(3)
            ]
            
            # Mock some tasks to fail
            meta_agent.decompose_task = AsyncMock(return_value=tasks)
            meta_agent.task_manager.add_tasks = AsyncMock()
            meta_agent.task_manager.get_next_tasks = AsyncMock(
                side_effect=[tasks, []]  # All tasks at once
            )
            meta_agent.task_manager._queue.get_all_tasks = AsyncMock(return_value=tasks)
            meta_agent.task_manager.get_critical_path = AsyncMock(return_value=[])
            meta_agent.task_manager.get_blocked_tasks = AsyncMock(return_value=[])
            meta_agent.task_manager.start_task = AsyncMock()
            meta_agent.task_manager.get_progress = AsyncMock(return_value={
                "completed_tasks": 1,
                "total_tasks": 3,
                "failed_tasks": 1
            })
            
            # Mock coordinator to simulate failures
            mock_agent = MagicMock()
            mock_agent.id = uuid4()
            mock_agent.role = MagicMock(value="core_logic")
            # Create a valid UUID for last_task_id
            last_task_uuid = uuid4()
            mock_agent.report_status = AsyncMock(return_value={
                "status": "idle",
                "current_task": None,
                "last_task_id": str(last_task_uuid),  # Provide a valid UUID string
                "produced_artifacts": [],
                "execution_time": 0
            })
            
            # Mock spawn_agent method on meta_agent - make sure first spawn succeeds
            # Create multiple mock agents for successful spawns
            mock_agent2 = MagicMock()
            mock_agent2.id = uuid4()
            mock_agent2.report_status = AsyncMock(return_value={
                "status": "idle",
                "current_task": None,
                "last_task_id": str(uuid4()),
                "produced_artifacts": [],
                "execution_time": 0
            })
            
            meta_agent.spawn_agent = AsyncMock(
                side_effect=[mock_agent, Exception("Spawn failed"), mock_agent2]
            )
            
            # Mock assign_task method on meta_agent
            meta_agent.assign_task = AsyncMock()
            
            # Mock coordinator methods
            meta_agent.coordinator.handle_task_completion = AsyncMock()
            meta_agent.coordinator.terminate_agent = AsyncMock()
            
            # One task should fail
            meta_agent.task_manager.fail_task = AsyncMock()
            meta_agent.task_manager.complete_task = AsyncMock()
            
            result = await meta_agent.process_request("Test concurrent failures")
            
            # Verify failure was handled
            meta_agent.task_manager.fail_task.assert_called()
    
    @pytest.mark.asyncio
    async def test_resource_exhaustion_handling(self):
        """Test handling of resource exhaustion."""
        with patch('src.agents.meta_agent.ClaudeClient'), \
             patch('src.agents.meta_agent.TaskManager'), \
             patch('src.agents.meta_agent.CommunicationHub'), \
             patch('src.agents.meta_agent.AgentCoordinator'):
            
            meta_agent = MetaAgent()
            # Mock coordinator.start method before initialize
            meta_agent.coordinator.start = AsyncMock()
            # Mock communication hub register_agent
            meta_agent.communication_hub.register_agent = AsyncMock()
            # Initialize context
            await meta_agent.initialize(TaskContext(
                project_root=Path("/tmp/test"),
                shared_memory={}
            ))
            
            # Simulate memory/resource limits
            meta_agent.coordinator.spawn_agent = AsyncMock(
                side_effect=MemoryError("Cannot allocate memory for new agent")
            )
            
            task = Task(name="Resource Heavy", description="Needs resources")
            meta_agent.decompose_task = AsyncMock(return_value=[task])
            meta_agent.task_manager.add_tasks = AsyncMock()
            meta_agent.task_manager.get_next_tasks = AsyncMock(
                side_effect=[[task], []]  # Return task once, then empty
            )
            
            # Mock fail_task to update the task status
            async def mock_fail_task(task_id, reason):
                if task_id == task.id:
                    task.status = TaskStatus.FAILED
            
            meta_agent.task_manager.fail_task = AsyncMock(side_effect=mock_fail_task)
            meta_agent.task_manager.get_blocked_tasks = AsyncMock(return_value=[])
            meta_agent.task_manager._queue.get_all_tasks = AsyncMock(return_value=[task])
            meta_agent.task_manager.get_critical_path = AsyncMock(return_value=[])
            meta_agent.task_manager.start_task = AsyncMock()
            meta_agent.task_manager.get_progress = AsyncMock(return_value={
                "completed_tasks": 0,
                "total_tasks": 1,
                "failed_tasks": 1
            })
            meta_agent.communication_hub.register_agent = AsyncMock()
            
            # Mock spawn_agent to fail with MemoryError for the first call, then succeed
            mock_agent = MagicMock()
            mock_agent.id = uuid4()
            mock_agent.role = MagicMock(value="core_logic")
            mock_agent.report_status = AsyncMock(return_value={
                "status": "idle",
                "current_task": None,
                "last_task_id": None,
                "produced_artifacts": [],
                "execution_time": 0
            })
            
            # First call fails, subsequent calls would succeed (but we'll only have one task)
            meta_agent.spawn_agent = AsyncMock(
                side_effect=[MemoryError("Cannot allocate memory for new agent")]
            )
            meta_agent.assign_task = AsyncMock()
            
            # The error should be caught and result in failed task
            result = await meta_agent.process_request("Heavy task")
            
            # Verify task was marked as failed
            meta_agent.task_manager.fail_task.assert_called()
            # The result.tasks_failed count comes from get_progress mock
            # which we've set to return failed_tasks: 1
    
    @pytest.mark.asyncio
    async def test_partial_result_recovery(self):
        """Test recovery and return of partial results on failure."""
        with patch('src.agents.meta_agent.ClaudeClient'), \
             patch('src.agents.meta_agent.TaskManager'), \
             patch('src.agents.meta_agent.CommunicationHub'), \
             patch('src.agents.meta_agent.AgentCoordinator'):
            
            meta_agent = MetaAgent()
            meta_agent.context = TaskContext(
                project_root=Path("/tmp/test"),
                shared_memory={}
            )
            # Mock coordinator.start method
            meta_agent.coordinator.start = AsyncMock()
            
            # Create tasks where some succeed and some fail
            tasks = [
                Task(name="Success 1", description="Will succeed"),
                Task(name="Fail", description="Will fail"),
                Task(name="Success 2", description="Will succeed"),
            ]
            
            # Mark some as completed
            tasks[0].status = TaskStatus.COMPLETED
            tasks[0].artifacts = [uuid4()]
            tasks[1].status = TaskStatus.FAILED
            tasks[2].status = TaskStatus.COMPLETED
            tasks[2].artifacts = [uuid4()]
            
            meta_agent.decompose_task = AsyncMock(return_value=tasks)
            meta_agent.task_manager.add_tasks = AsyncMock()
            meta_agent.task_manager._queue.get_all_tasks = AsyncMock(return_value=tasks)
            meta_agent.task_manager.get_critical_path = AsyncMock(return_value=[])
            meta_agent.task_manager.get_next_tasks = AsyncMock(return_value=[])  # No more tasks to execute
            meta_agent.task_manager.get_blocked_tasks = AsyncMock(return_value=[])
            meta_agent.task_manager.get_progress = AsyncMock(return_value={
                "completed_tasks": 2,
                "total_tasks": 3,
                "failed_tasks": 1
            })
            
            # Should return partial results
            result = await meta_agent.process_request("Partial success")
            
            assert result.tasks_completed == 2
            assert result.tasks_failed == 1
            assert result.success_rate == 2/3