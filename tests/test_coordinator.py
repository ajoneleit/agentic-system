"""Tests for agent coordinator functionality."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.coordinator import AgentCoordinator, AgentStatus
from src.core.interfaces import (
    AgentRole,
    Task,
    TaskContext,
    TaskPriority,
)


class TestAgentCoordinator:
    """Test agent coordinator functionality."""

    @pytest.fixture
    def coordinator(self):
        """Create coordinator instance."""
        with patch('src.core.coordinator.CommunicationHub'), \
             patch('src.core.coordinator.TaskManager'):
            mock_task_manager = MagicMock()
            mock_communication_hub = MagicMock()

            coordinator = AgentCoordinator(
                task_manager=mock_task_manager,
                communication_hub=mock_communication_hub,
                max_agents=5,
            )
            yield coordinator

    @pytest.mark.asyncio
    async def test_spawn_agent(self, coordinator):
        """Test spawning new agents."""
        context = TaskContext(
            project_root=Path("/tmp/test"),
            shared_memory={}
        )

        # Register agent factory first
        mock_agent_class = MagicMock()
        mock_agent = MagicMock()
        mock_agent.id = uuid4()
        mock_agent.initialize = AsyncMock()
        mock_agent_class.return_value = mock_agent

        coordinator.register_agent_factory(AgentRole.CORE_LOGIC, mock_agent_class)
        coordinator.communication_hub.register_agent = AsyncMock()

        # Spawn agent
        agent = await coordinator.spawn_agent(
            AgentRole.CORE_LOGIC,
            context,
            metadata={"test": True}
        )

        assert mock_agent_class.called
        assert mock_agent.initialize.called
        assert coordinator.communication_hub.register_agent.called

    @pytest.mark.asyncio
    async def test_spawn_agent_limit(self, coordinator):
        """Test agent spawn limit enforcement."""
        coordinator.max_agents = 2
        context = TaskContext(
            project_root=Path("/tmp/test"),
            shared_memory={}
        )

        # Spawn maximum agents
        for i in range(2):
            agent = MagicMock()
            agent.id = uuid4()
            coordinator._agents[agent.id] = agent

        # Should raise error when limit exceeded
        from src.core.exceptions import AgentOverloadError
        with pytest.raises(AgentOverloadError):
            await coordinator.spawn_agent(
                AgentRole.CORE_LOGIC,
                context,
                metadata={}
            )

    @pytest.mark.asyncio
    async def test_terminate_agent(self, coordinator):
        """Test agent termination."""
        agent = MagicMock()
        agent.id = uuid4()
        agent.shutdown = AsyncMock()

        coordinator._agents[agent.id] = agent
        coordinator._agent_status[agent.id] = AgentStatus.IDLE
        coordinator._agent_tasks[agent.id] = set([uuid4()])
        coordinator.communication_hub.unregister_agent = AsyncMock()

        # Terminate agent - returns None, not success boolean
        await coordinator.terminate_agent(agent.id)

        assert agent.id not in coordinator._agents
        assert agent.id not in coordinator._agent_tasks
        agent.shutdown.assert_called_once()
        coordinator.communication_hub.unregister_agent.assert_called_once_with(agent.id)

    @pytest.mark.asyncio
    async def test_terminate_nonexistent_agent(self, coordinator):
        """Test terminating non-existent agent."""
        fake_id = uuid4()

        # Should not raise error, just return None
        await coordinator.terminate_agent(fake_id)

        # Nothing to assert - method returns None

    @pytest.mark.asyncio
    async def test_assign_task(self, coordinator):
        """Test task assignment to agent."""
        agent = MagicMock()
        agent.id = uuid4()

        coordinator._agents[agent.id] = agent
        coordinator._agent_tasks[agent.id] = set()
        coordinator._agent_status[agent.id] = AgentStatus.IDLE
        coordinator.communication_hub.send_message = AsyncMock()

        task = Task(
            name="Test Task",
            description="Test",
            priority=TaskPriority.HIGH,
        )

        # Assign task
        await coordinator.assign_task(agent.id, task)

        assert task.id in coordinator._agent_tasks[agent.id]
        assert coordinator._agent_status[agent.id] == AgentStatus.WORKING
        coordinator.communication_hub.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_task_completion(self, coordinator):
        """Test handling task completion."""
        agent_id = uuid4()
        task_id = uuid4()

        # Set up agent with task
        coordinator._agent_tasks[agent_id] = {task_id}
        coordinator._agent_status[agent_id] = AgentStatus.WORKING

        # Mock agent metrics
        mock_metrics = MagicMock()
        mock_metrics.update_task_completion = MagicMock()
        coordinator._agent_metrics[agent_id] = mock_metrics

        # Complete task
        await coordinator.handle_task_completion(
            agent_id,
            task_id,
            success=True,
            execution_time=10.5
        )

        assert task_id not in coordinator._agent_tasks[agent_id]
        assert coordinator._agent_status[agent_id] == AgentStatus.IDLE
        mock_metrics.update_task_completion.assert_called_once_with(True, 10.5)


    @pytest.mark.asyncio
    async def test_get_system_status(self, coordinator):
        """Test getting system status."""
        # Set up system state
        agent1 = MagicMock()
        agent1.id = uuid4()
        agent1.role = AgentRole.CORE_LOGIC

        agent2 = MagicMock()
        agent2.id = uuid4()
        agent2.role = AgentRole.TESTING

        coordinator._agents = {
            agent1.id: agent1,
            agent2.id: agent2,
        }

        coordinator._agent_status = {
            agent1.id: AgentStatus.WORKING,
            agent2.id: AgentStatus.IDLE,
        }

        coordinator._agent_tasks = {
            agent1.id: {uuid4()},
            agent2.id: set(),
        }

        # Mock agent metrics
        metrics1 = MagicMock()
        metrics1.tasks_completed = 5
        metrics1.success_rate = 0.8
        metrics1.average_task_time = 10.0

        coordinator._agent_metrics = {
            agent1.id: metrics1,
        }

        # Get status
        status = await coordinator.get_system_status()

        assert status["total_agents"] == 2
        assert status["max_agents"] == 5
        assert status["total_active_tasks"] == 1  # One agent has 1 task
        assert status["agent_status_breakdown"]["working"] == 1
        assert status["agent_status_breakdown"]["idle"] == 1
        assert len(status["agents"]) == 2

    @pytest.mark.asyncio
    async def test_stop_coordinator(self, coordinator):
        """Test coordinator shutdown."""
        # Set up agents
        agent1 = MagicMock()
        agent1.id = uuid4()
        agent1.shutdown = AsyncMock()

        agent2 = MagicMock()
        agent2.id = uuid4()
        agent2.shutdown = AsyncMock()

        coordinator._agents = {
            agent1.id: agent1,
            agent2.id: agent2,
        }

        coordinator._agent_status = {
            agent1.id: AgentStatus.IDLE,
            agent2.id: AgentStatus.IDLE,
        }

        coordinator._agent_tasks = {
            agent1.id: set(),
            agent2.id: set(),
        }

        coordinator.communication_hub.unregister_agent = AsyncMock()

        # Stop coordinator
        await coordinator.stop()

        # All agents should be shut down
        agent1.shutdown.assert_called_once()
        agent2.shutdown.assert_called_once()
        assert len(coordinator._agents) == 0
