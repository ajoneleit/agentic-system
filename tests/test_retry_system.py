"""Tests for the integrated retry system."""

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.agents.meta_agent import MetaAgent
from src.core.exceptions import TaskError
from src.core.failure_analyzer import (
    ErrorDiagnosis,
    ErrorType,
    FailureAnalyzer,
    RetryStrategy,
)
from src.core.interfaces import (
    AgentRole,
    Task,
    TaskContext,
    TaskPriority,
    TaskStatus,
)
from src.core.task_result import TaskResult


@pytest.fixture
def meta_agent():
    """Create a MetaAgent instance for testing."""
    agent = MetaAgent(artifact_storage_path=Path("/tmp/test_projects"))
    return agent


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return Task(
        id=uuid4(),
        name="Test Task",
        description="Generate a test function",
        required_role=AgentRole.CORE_LOGIC,
        priority=TaskPriority.HIGH,
        dependencies=[],
    )


@pytest.fixture
def task_context():
    """Create a task context for testing."""
    return TaskContext(
        project_root=Path("/tmp/test_project"),
        shared_memory={},
        artifact_manager=None,
    )


class TestFailureAnalyzer:
    """Test the FailureAnalyzer component."""
    
    @pytest.mark.asyncio
    async def test_analyze_cli_error(self):
        """Test analysis of CLI malformed response error."""
        analyzer = FailureAnalyzer()
        task = Task(
            id=uuid4(),
            name="Test Task",
            description="Test",
            required_role=AgentRole.CORE_LOGIC,
        )
        
        error = Exception("Failed to parse Claude response as JSON")
        context = {
            "cli_response": "Invalid JSON...",  # 15 characters
            "attempt": 1,
        }
        
        diagnosis = await analyzer.analyze_error(task, error, context)
        
        assert diagnosis.error_type == ErrorType.CLI_MALFORMED_RESPONSE
        assert diagnosis.is_retryable is True
        assert diagnosis.retry_strategy == RetryStrategy.MODIFY_PROMPT
        assert "15-character CLI response" in diagnosis.patterns_matched
    
    @pytest.mark.asyncio
    async def test_analyze_api_rate_limit(self):
        """Test analysis of API rate limit error."""
        analyzer = FailureAnalyzer()
        task = Task(
            id=uuid4(),
            name="Test Task",
            description="Test",
            required_role=AgentRole.CORE_LOGIC,
        )
        
        error = Exception("429 Too Many Requests")
        context = {"attempt": 1}
        
        diagnosis = await analyzer.analyze_error(task, error, context)
        
        assert diagnosis.error_type == ErrorType.API_RATE_LIMIT
        assert diagnosis.is_retryable is True
        assert diagnosis.retry_strategy == RetryStrategy.EXPONENTIAL_BACKOFF
    
    @pytest.mark.asyncio
    async def test_generate_fix_prompt(self):
        """Test fix prompt generation."""
        analyzer = FailureAnalyzer()
        task = Task(
            id=uuid4(),
            name="Test Task",
            description="Generate a calculator function",
            required_role=AgentRole.CORE_LOGIC,
        )
        
        diagnosis = ErrorDiagnosis(
            error_type=ErrorType.CLI_MALFORMED_RESPONSE,
            error_message="Failed to parse JSON",
            is_retryable=True,
            retry_strategy=RetryStrategy.MODIFY_PROMPT,
        )
        
        new_prompt = await analyzer.generate_fix_prompt(task, diagnosis)
        
        assert "JSON format" in new_prompt
        assert "calculator function" in new_prompt
        assert "{" in new_prompt and "}" in new_prompt


class TestMetaAgentRetry:
    """Test MetaAgent retry functionality."""
    
    @pytest.mark.asyncio
    async def test_task_retry_on_failure(self, meta_agent, sample_task, task_context):
        """Test that tasks are retried on failure."""
        # Mock the agent
        mock_agent = MagicMock()
        mock_agent.id = uuid4()
        mock_agent.execute_task = AsyncMock()
        
        # First two attempts fail, third succeeds
        error_result = TaskResult(
            task_id=sample_task.id,
            agent_id=mock_agent.id,
            success=False,
        )
        error_result.add_error("Test error")
        
        success_result = TaskResult(
            task_id=sample_task.id,
            agent_id=mock_agent.id,
            success=True,
        )
        
        mock_agent.execute_task.side_effect = [
            error_result,
            error_result,
            success_result,
        ]
        
        # Execute task with retry
        result = await meta_agent._execute_task_with_retry(
            sample_task, mock_agent, task_context
        )
        
        assert result.success is True
        assert mock_agent.execute_task.call_count == 3
        assert meta_agent._task_retry_counts[sample_task.id] == 2
    
    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self, meta_agent, sample_task, task_context):
        """Test behavior when max retries are exhausted."""
        # Set max retries to 2
        meta_agent.max_retries = 2
        
        # Mock agent that always fails
        mock_agent = MagicMock()
        mock_agent.id = uuid4()
        mock_agent.execute_task = AsyncMock()
        
        error_result = TaskResult(
            task_id=sample_task.id,
            agent_id=mock_agent.id,
            success=False,
        )
        error_result.add_error("Persistent error")
        
        mock_agent.execute_task.return_value = error_result
        
        # Execute task with retry
        result = await meta_agent._execute_task_with_retry(
            sample_task, mock_agent, task_context
        )
        
        assert result.success is False
        assert mock_agent.execute_task.call_count == 2
        assert "Failed after 2 attempts" in result.errors[0]
    
    @pytest.mark.asyncio
    async def test_retry_delay_calculation(self, meta_agent, sample_task):
        """Test exponential backoff calculation."""
        # Test base delay
        delay = await meta_agent._calculate_retry_delay(sample_task, Exception(), 1)
        assert delay == meta_agent.retry_delay
        
        # Test exponential backoff
        delay = await meta_agent._calculate_retry_delay(sample_task, Exception(), 2)
        assert delay == meta_agent.retry_delay * meta_agent.retry_backoff
        
        delay = await meta_agent._calculate_retry_delay(sample_task, Exception(), 3)
        assert delay == meta_agent.retry_delay * (meta_agent.retry_backoff ** 2)
        
        # Test max delay cap
        delay = await meta_agent._calculate_retry_delay(sample_task, Exception(), 10)
        assert delay <= 60.0
    
    @pytest.mark.asyncio
    async def test_task_prompt_modification(self, meta_agent, sample_task):
        """Test that task prompts are modified based on failure diagnosis."""
        original_description = sample_task.description
        
        # Create retry history with CLI error
        meta_agent._task_retry_history[sample_task.id] = [{
            "diagnosis": ErrorDiagnosis(
                error_type=ErrorType.CLI_MALFORMED_RESPONSE,
                error_message="Failed to parse JSON",
                is_retryable=True,
                retry_strategy=RetryStrategy.MODIFY_PROMPT,
            )
        }]
        
        await meta_agent._prepare_task_for_retry(sample_task, Exception(), 2)
        
        # Check that prompt was modified
        assert sample_task.description != original_description
        assert "JSON format" in sample_task.description
    
    @pytest.mark.asyncio
    async def test_deadlock_resolution(self, meta_agent, task_context):
        """Test deadlock resolution by retrying failed prerequisites."""
        # Create tasks with dependencies
        task1 = Task(
            id=uuid4(),
            name="Task 1",
            description="First task",
            required_role=AgentRole.CORE_LOGIC,
            dependencies=[],
        )
        
        task2 = Task(
            id=uuid4(),
            name="Task 2",
            description="Second task",
            required_role=AgentRole.CORE_LOGIC,
            dependencies=[task1.id],
        )
        
        # Mock task manager
        meta_agent.task_manager.reset_task = AsyncMock(return_value=True)
        
        # Try to resolve deadlock
        failed_tasks = {task1.id}
        blocked_tasks = [task2]
        all_tasks = [task1, task2]
        
        resolved = await meta_agent._try_resolve_deadlock(
            blocked_tasks, failed_tasks, all_tasks, task_context
        )
        
        assert resolved is True
        assert meta_agent.task_manager.reset_task.called
        assert task1.id not in failed_tasks
        assert meta_agent._task_retry_counts[task1.id] == 0


class TestRetryIntegration:
    """Test retry integration with the full system."""
    
    @pytest.mark.asyncio
    async def test_project_result_includes_retry_info(self, meta_agent):
        """Test that ProjectResult includes retry information."""
        # Set up retry counts and history
        task_id = uuid4()
        meta_agent._task_retry_counts[task_id] = 2
        meta_agent._task_retry_history[task_id] = [
            {
                "attempt": 1,
                "error": "First error",
                "timestamp": datetime.utcnow().isoformat(),
            },
            {
                "attempt": 2,
                "error": "Second error",
                "timestamp": datetime.utcnow().isoformat(),
            },
        ]
        
        # Create task results
        task_results = {
            task_id: TaskResult(
                task_id=task_id,
                agent_id=uuid4(),
                success=False,
                errors=["Final error"],
            )
        }
        
        # Aggregate results
        result = await meta_agent.aggregate_results(task_results)
        
        assert task_id in result.retry_summary
        assert result.retry_summary[task_id] == 2
        assert len(result.failure_reports) == 1
        assert result.failure_reports[0]["retry_count"] == 2
        assert result.failure_reports[0]["attempts"] == meta_agent._task_retry_history[task_id]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])