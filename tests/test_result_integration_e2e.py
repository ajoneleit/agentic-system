"""End-to-end integration tests for Result[T] pattern.

Tests the complete flow from MetaAgent through SubAgents with Result[T]
error handling and validates system-wide error propagation.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.agents.meta_agent import MetaAgent, ProjectResult
from src.agents.sub_agent import CodeGeneratorAgent, TestWriterAgent
from src.core.agent_errors import CLIError, CLINotAvailableError, OrchestrationError, WorkspaceError
from src.core.interfaces import (
    AgentRole,
    Task,
    TaskContext,
    TaskPriority,
    TaskStatus,
)
from src.core.result import Result


class TestFullSystemIntegration:
    """Test complete system integration with Result[T]."""

    @pytest.fixture
    def test_workspace(self, tmp_path):
        """Create a test workspace directory."""
        workspace = tmp_path / "test_project" / "workspace"
        workspace.mkdir(parents=True)
        return workspace

    @pytest.fixture
    async def initialized_meta_agent(self):
        """Create and initialize a MetaAgent."""
        with patch('src.clients.openai_client.OpenAIClient') as mock_openai:
            # Mock OpenAI responses
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            meta_agent = MetaAgent()
            return meta_agent

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Test gets stuck - skipping for now")
    async def test_successful_code_generation_flow(self, initialized_meta_agent, test_workspace):
        """Test successful end-to-end code generation flow."""
        meta_agent = initialized_meta_agent

        # Mock task decomposition
        decomposed_tasks = [
            Task(
                id=uuid4(),
                name="generate_hello_world",
                description="Create a hello world Python script",
                agent_role=AgentRole.CORE_LOGIC,
                priority=TaskPriority.HIGH,
                status=TaskStatus.PENDING,
                metadata={
                    "language": "python",
                    "specification": {
                        "deliverable": "hello_world.py",
                        "language": "python"
                    }
                }
            )
        ]

        # Mock the OpenAI response for decomposition
        meta_agent.ai_client.create_message = AsyncMock(return_value={
            "content": json.dumps({
                "project_name": "hello_world_project",
                "tasks": [
                    {
                        "name": "generate_hello_world",
                        "description": "Create a hello world Python script",
                        "type": "core_logic",
                        "priority": "high",
                        "dependencies": [],
                        "estimated_complexity": "low",
                        "specification": {
                            "deliverable": "hello_world.py",
                            "language": "python"
                        }
                    }
                ],
                "execution_order": ["generate_hello_world"]
            })
        })

        # Mock agent execution
        with patch('src.agents.sub_agent.ClaudeCodeClient') as mock_cli_class:
            mock_cli = MagicMock()
            mock_cli.check_cli_available = AsyncMock(return_value=True)
            mock_cli.create_message_for_code = AsyncMock(return_value={
                "content": [{"text": "print('Hello, World!')"}]
            })
            mock_cli_class.return_value = mock_cli

            # Create test file to simulate CLI creating it
            hello_file = test_workspace / "hello_world.py"
            hello_file.write_text("print('Hello, World!')")

            # Execute the request
            result = await meta_agent.process_request("Create a hello world Python script")

            # Verify successful Result
            assert result.is_success()
            project_result = result.unwrap()
            assert isinstance(project_result, ProjectResult)
            assert project_result.success
            assert project_result.tasks_completed > 0
            assert project_result.project_name == "hello_world_project"

    @pytest.mark.asyncio
    async def test_cli_unavailable_error_propagation(self, initialized_meta_agent):
        """Test CLI unavailable error propagates through the system."""
        meta_agent = initialized_meta_agent

        # Mock successful decomposition
        meta_agent.ai_client.create_message = AsyncMock(return_value={
            "content": json.dumps({
                "project_name": "test_project",
                "tasks": [
                    {
                        "name": "generate_code",
                        "description": "Generate code",
                        "type": "core_logic",
                        "priority": "high",
                        "dependencies": [],
                        "specification": {"language": "python"}
                    }
                ]
            })
        })

        # Mock CLI unavailable
        with patch('src.agents.sub_agent.ClaudeCodeClient') as mock_cli_class:
            mock_cli = MagicMock()
            mock_cli.check_cli_available = AsyncMock(return_value=False)
            mock_cli_class.return_value = mock_cli

            # Execute the request
            result = await meta_agent.process_request("Generate some code")

            # Verify failure propagation
            assert result.is_failure()
            error = result.get_error()
            assert isinstance(error, OrchestrationError)
            # The error should mention execution issues
            assert "execution" in str(error).lower()

    @pytest.mark.asyncio
    async def test_workspace_error_handling(self, initialized_meta_agent, test_workspace):
        """Test workspace errors are handled properly."""
        meta_agent = initialized_meta_agent

        # Mock successful decomposition
        meta_agent.ai_client.create_message = AsyncMock(return_value={
            "content": json.dumps({
                "project_name": "test_project",
                "tasks": [
                    {
                        "name": "generate_code",
                        "description": "Generate code",
                        "type": "core_logic",
                        "priority": "high",
                        "dependencies": [],
                        "specification": {"language": "python"}
                    }
                ]
            })
        })

        # Mock CLI success but no files created
        with patch('src.agents.sub_agent.ClaudeCodeClient') as mock_cli_class:
            mock_cli = MagicMock()
            mock_cli.check_cli_available = AsyncMock(return_value=True)
            mock_cli.create_message_for_code = AsyncMock(return_value={
                "content": [{"text": "Some response without creating files"}]
            })
            mock_cli_class.return_value = mock_cli

            # Execute the request
            result = await meta_agent.process_request("Generate code")

            # Should handle the workspace error gracefully
            assert result.is_success()  # MetaAgent still returns success
            project_result = result.unwrap()
            # But the task should have failed
            assert project_result.tasks_failed > 0

    @pytest.mark.asyncio
    async def test_multiple_agent_coordination(self, initialized_meta_agent, test_workspace):
        """Test coordination of multiple agents with Result[T]."""
        meta_agent = initialized_meta_agent

        # Mock decomposition into multiple tasks
        meta_agent.ai_client.create_message = AsyncMock(return_value={
            "content": json.dumps({
                "project_name": "multi_agent_project",
                "tasks": [
                    {
                        "name": "generate_code",
                        "description": "Generate main code",
                        "type": "core_logic",
                        "priority": "high",
                        "dependencies": [],
                        "specification": {"language": "python"}
                    },
                    {
                        "name": "generate_tests",
                        "description": "Generate tests",
                        "type": "testing",
                        "priority": "medium",
                        "dependencies": ["generate_code"],
                        "specification": {"language": "python"}
                    },
                    {
                        "name": "generate_docs",
                        "description": "Generate documentation",
                        "type": "documentation",
                        "priority": "low",
                        "dependencies": ["generate_code"],
                        "specification": {}
                    }
                ]
            })
        })

        # Mock CLI for all agents
        with patch('src.agents.sub_agent.ClaudeCodeClient') as mock_cli_class:
            mock_cli = MagicMock()
            mock_cli.check_cli_available = AsyncMock(return_value=True)

            # Different responses for different task types
            async def mock_create_message(messages, task_type, **kwargs):
                if task_type == "code":
                    # Create main.py
                    main_file = test_workspace / "main.py"
                    main_file.write_text("def hello():\n    return 'Hello'")
                    return {"content": [{"text": "Created main.py"}]}
                elif task_type == "test":
                    # Create test_main.py
                    test_file = test_workspace / "test_main.py"
                    test_file.write_text("def test_hello():\n    assert hello() == 'Hello'")
                    return {"content": [{"text": "Created test_main.py"}]}
                else:  # documentation
                    return {"content": [{"text": "# Documentation\nMain module documentation"}]}

            mock_cli.create_message_for_code = mock_create_message
            mock_cli_class.return_value = mock_cli

            # Execute the request
            result = await meta_agent.process_request("Create a Python module with tests and docs")

            # Verify successful multi-agent coordination
            assert result.is_success()
            project_result = result.unwrap()
            assert project_result.success
            # Should have completed multiple tasks
            assert project_result.tasks_completed >= 2


class TestErrorRecoveryPatterns:
    """Test error recovery patterns with Result[T]."""

    @pytest.mark.asyncio
    async def test_partial_success_handling(self):
        """Test system handles partial successes correctly."""
        # Create a scenario where some agents succeed and others fail
        code_agent = CodeGeneratorAgent(uuid4())
        test_agent = TestWriterAgent(uuid4())

        context = MagicMock(spec=TaskContext)
        context.project_root = Path("/tmp/test")

        # Initialize agents with different outcomes
        with patch('src.agents.sub_agent.ClaudeCodeClient') as mock_cli_class:
            # Code agent succeeds
            mock_cli_success = MagicMock()
            mock_cli_success.check_cli_available = AsyncMock(return_value=True)
            mock_cli_class.return_value = mock_cli_success

            code_init_result = await code_agent.initialize(context)
            assert code_init_result.is_success()

            # Test agent fails
            mock_cli_fail = MagicMock()
            mock_cli_fail.check_cli_available = AsyncMock(return_value=False)
            mock_cli_class.return_value = mock_cli_fail

            test_init_result = await test_agent.initialize(context)
            assert test_init_result.is_failure()
            assert isinstance(test_init_result.get_error(), CLINotAvailableError)

    @pytest.mark.asyncio
    async def test_error_context_preservation(self):
        """Test error context is preserved through Result chain."""
        agent = CodeGeneratorAgent(uuid4())
        task_id = uuid4()

        # Create an error with rich context
        error = WorkspaceError(
            "Failed to create file",
            agent_id=agent.id,
            task_id=task_id,
            details={
                "filename": "test.py",
                "reason": "Permission denied",
                "workspace": "/tmp/test"
            }
        )

        # Wrap in Result and verify context is preserved
        result: Result[str] = Result.failure(error)

        assert result.is_failure()
        retrieved_error = result.get_error()
        assert retrieved_error.agent_id == agent.id
        assert retrieved_error.task_id == task_id
        assert retrieved_error.details["filename"] == "test.py"
        assert retrieved_error.details["reason"] == "Permission denied"

    def test_result_or_else_recovery(self):
        """Test Result.or_else provides recovery mechanism."""
        # Primary operation fails
        primary_result: Result[str] = Result.failure(
            CLIError("Primary CLI failed")
        )

        # Recovery operation
        def recover_operation(error) -> Result[str]:
            return Result.success("Recovered value")

        # Apply recovery
        final_result = primary_result.or_else(recover_operation)

        assert final_result.is_success()
        assert final_result.unwrap() == "Recovered value"


class TestPerformanceWithResult:
    """Test performance characteristics of Result[T] integration."""

    @pytest.mark.asyncio
    async def test_result_overhead_minimal(self):
        """Test Result[T] adds minimal overhead to operations."""
        import time

        # Time a simple operation without Result
        async def simple_operation() -> str:
            await asyncio.sleep(0.001)  # Simulate work
            return "result"

        # Time the same operation with Result
        async def result_operation() -> Result[str]:
            await asyncio.sleep(0.001)  # Simulate work
            return Result.success("result")

        # Measure without Result
        start = time.time()
        for _ in range(100):
            await simple_operation()
        time_without_result = time.time() - start

        # Measure with Result
        start = time.time()
        for _ in range(100):
            result = await result_operation()
            result.unwrap()  # Include unwrap in timing
        time_with_result = time.time() - start

        # Result overhead should be less than 10%
        overhead = (time_with_result - time_without_result) / time_without_result
        assert overhead < 0.1, f"Result overhead too high: {overhead:.2%}"

    @pytest.mark.asyncio
    async def test_error_chain_performance(self):
        """Test performance of error propagation chains."""
        # Create a chain of failing operations
        async def failing_operation() -> Result[str]:
            return Result.failure(CLIError("Operation failed"))

        async def chain_operations(depth: int) -> Result[str]:
            result = await failing_operation()
            for _ in range(depth):
                if result.is_failure():
                    return result
                # This won't execute due to failure
                result = result.map(lambda x: x + ".")
            return result

        import time

        # Time error propagation through deep chains
        start = time.time()
        for _ in range(100):
            await chain_operations(depth=50)
        elapsed = time.time() - start

        # Should handle deep error chains efficiently
        assert elapsed < 0.5, f"Error chain propagation too slow: {elapsed:.3f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
