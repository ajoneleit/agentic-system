"""Unit tests for Result[T] integration in agents.

Tests verify that all agent methods properly use the Result[T] pattern
for error handling and that errors propagate correctly through the system.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
from pathlib import Path

from src.agents.sub_agent import (
    SubAgent, 
    CodeGeneratorAgent,
    TestWriterAgent,
    DocumentationAgent,
    DebugAgent,
    RefactorAgent
)
from src.agents.meta_agent import MetaAgent, ProjectResult
from src.core.interfaces import (
    Task,
    TaskContext,
    TaskStatus,
    TaskPriority,
    AgentRole,
    Artifact,
    ArtifactType
)
from src.core.result import Result
from src.core.agent_errors import (
    AgentResultError,
    CLIError,
    CLINotAvailableError,
    CLIResponseError,
    WorkspaceError,
    MetaAgentError,
    OrchestrationError,
    ResultAggregationError,
    CodeGenerationError,
    TaskDecompositionError
)


class TestSubAgentResultIntegration:
    """Test SubAgent base class Result[T] integration."""
    
    @pytest.fixture
    def sub_agent(self):
        """Create a concrete SubAgent instance for testing."""
        agent = CodeGeneratorAgent(uuid4())
        return agent
    
    @pytest.fixture
    def task_context(self, tmp_path):
        """Create a test task context."""
        # Create workspace directory
        workspace = tmp_path / "workspace"
        workspace.mkdir(exist_ok=True)
        
        context = MagicMock(spec=TaskContext)
        context.project_root = tmp_path
        context.shared_memory = {}
        context.global_constraints = {}
        context.artifact_manager = None
        return context
    
    @pytest.fixture
    def test_task(self):
        """Create a test task."""
        return Task(
            id=uuid4(),
            name="test_task",
            description="Test task description",
            agent_role=AgentRole.CORE_LOGIC,
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.PENDING,
            dependencies=[],
            metadata={"language": "python"}
        )
    
    @pytest.mark.asyncio
    async def test_initialize_returns_result_success(self, sub_agent, task_context):
        """Test initialize returns Result.success on successful initialization."""
        # Need to patch where ClaudeCodeClient is imported in sub_agent module
        with patch('src.agents.sub_agent.ClaudeCodeClient') as mock_cli_class:
            mock_cli = MagicMock()
            mock_cli.check_cli_available = AsyncMock(return_value=True)
            mock_cli_class.return_value = mock_cli
            
            result = await sub_agent.initialize(task_context)
            
            assert result.is_success()
            assert sub_agent._is_initialized
            assert sub_agent.context == task_context
    
    @pytest.mark.asyncio
    async def test_initialize_returns_result_failure_when_cli_unavailable(self, sub_agent, task_context):
        """Test initialize returns Result.failure when CLI is not available."""
        with patch('src.agents.sub_agent.ClaudeCodeClient') as mock_cli_class:
            mock_cli = MagicMock()
            mock_cli.check_cli_available = AsyncMock(return_value=False)
            mock_cli_class.return_value = mock_cli
            
            result = await sub_agent.initialize(task_context)
            
            assert result.is_failure()
            assert isinstance(result.get_error(), CLINotAvailableError)
            assert not sub_agent._is_initialized
    
    @pytest.mark.asyncio
    async def test_execute_task_returns_result_failure_when_not_initialized(self, sub_agent, test_task, task_context):
        """Test execute_task returns Result.failure when agent not initialized."""
        result = await sub_agent.execute_task(test_task, task_context)
        
        assert result.is_failure()
        assert isinstance(result.get_error(), AgentResultError)
        assert "not initialized" in str(result.get_error())
    
    @pytest.mark.asyncio
    async def test_execute_task_propagates_specific_task_failure(self, sub_agent, test_task, task_context):
        """Test execute_task propagates failures from _execute_specific_task."""
        # Initialize agent first
        with patch('src.agents.sub_agent.ClaudeCodeClient') as mock_cli_class:
            mock_cli = MagicMock()
            mock_cli.check_cli_available = AsyncMock(return_value=True)
            mock_cli_class.return_value = mock_cli
            await sub_agent.initialize(task_context)
        
        # Mock _execute_specific_task to return failure
        error = CodeGenerationError("Code generation failed", agent_id=sub_agent.id)
        sub_agent._execute_specific_task = AsyncMock(
            return_value=Result.failure(error)
        )
        
        result = await sub_agent.execute_task(test_task, task_context)
        
        assert result.is_failure()
        assert result.get_error() == error
    
    @pytest.mark.asyncio
    async def test_query_claude_returns_result_success(self, sub_agent, task_context):
        """Test _query_claude returns Result.success on successful query."""
        # Initialize agent with mocked CLI
        with patch('src.agents.sub_agent.ClaudeCodeClient') as mock_cli_class:
            mock_cli = MagicMock()
            mock_cli.check_cli_available = AsyncMock(return_value=True)
            mock_cli_class.return_value = mock_cli
            await sub_agent.initialize(task_context)
            
            # Mock CLI response
            mock_cli.create_message_for_code = AsyncMock(return_value={
                "content": [{"text": "Generated code"}]
            })
            
            result = await sub_agent._query_claude("Test prompt")
            
            assert result.is_success()
            assert result.unwrap() == "Generated code"
    
    @pytest.mark.asyncio
    async def test_query_claude_returns_result_failure_on_empty_response(self, sub_agent, task_context):
        """Test _query_claude returns Result.failure on empty response."""
        # Initialize agent with mocked CLI
        with patch('src.agents.sub_agent.ClaudeCodeClient') as mock_cli_class:
            mock_cli = MagicMock()
            mock_cli.check_cli_available = AsyncMock(return_value=True)
            mock_cli_class.return_value = mock_cli
            await sub_agent.initialize(task_context)
            
            # Mock empty CLI response
            mock_cli.create_message_for_code = AsyncMock(return_value={
                "content": [{"text": ""}]
            })
            
            result = await sub_agent._query_claude("Test prompt")
            
            assert result.is_failure()
            assert isinstance(result.get_error(), CLIResponseError)


class TestCodeGeneratorAgentResult:
    """Test CodeGeneratorAgent Result[T] integration."""
    
    @pytest.fixture
    def code_agent(self):
        """Create a CodeGeneratorAgent instance."""
        return CodeGeneratorAgent(uuid4())
    
    @pytest.fixture
    def workspace_dir(self, tmp_path):
        """Create a test workspace directory."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        return workspace
    
    @pytest.fixture
    def test_task(self):
        """Create a test task."""
        return Task(
            id=uuid4(),
            name="test_task",
            description="Test task description",
            agent_role=AgentRole.CORE_LOGIC,
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.PENDING,
            dependencies=[],
            metadata={"language": "python"}
        )
    
    @pytest.mark.asyncio
    async def test_execute_specific_task_returns_result_success(self, code_agent, test_task, task_context, workspace_dir):
        """Test _execute_specific_task returns Result.success with artifacts."""
        # Initialize agent
        with patch('src.agents.sub_agent.ClaudeCodeClient') as mock_cli_class:
            mock_cli = MagicMock()
            mock_cli.check_cli_available = AsyncMock(return_value=True)
            mock_cli_class.return_value = mock_cli
            await code_agent.initialize(task_context)
            
            # Mock successful code generation
            code_agent._query_claude = AsyncMock(
                return_value=Result.success("print('Hello World')")
            )
            
            # Create a test file in workspace
            test_file = workspace_dir / "test.py"
            test_file.write_text("print('Hello World')")
            
            result = await code_agent._execute_specific_task(test_task, task_context)
            
            assert result.is_success()
            artifacts = result.unwrap()
            assert len(artifacts) > 0
            assert all(isinstance(a, Artifact) for a in artifacts)
    
    @pytest.mark.asyncio
    async def test_execute_specific_task_propagates_cli_failure(self, code_agent, test_task, task_context):
        """Test _execute_specific_task propagates CLI query failures."""
        # Initialize agent
        with patch('src.agents.sub_agent.ClaudeCodeClient') as mock_cli_class:
            mock_cli = MagicMock()
            mock_cli.check_cli_available = AsyncMock(return_value=True)
            mock_cli_class.return_value = mock_cli
            await code_agent.initialize(task_context)
            
            # Mock CLI failure
            cli_error = CLIError("CLI failed", agent_id=code_agent.id)
            code_agent._query_claude = AsyncMock(
                return_value=Result.failure(cli_error)
            )
            
            result = await code_agent._execute_specific_task(test_task, task_context)
            
            assert result.is_failure()
            assert result.get_error() == cli_error
    
    @pytest.mark.asyncio
    async def test_execute_specific_task_returns_workspace_error_on_no_files(self, code_agent, test_task, task_context, workspace_dir):
        """Test _execute_specific_task returns WorkspaceError when no files created."""
        # Initialize agent
        with patch('src.agents.sub_agent.ClaudeCodeClient') as mock_cli_class:
            mock_cli = MagicMock()
            mock_cli.check_cli_available = AsyncMock(return_value=True)
            mock_cli_class.return_value = mock_cli
            await code_agent.initialize(task_context)
            
            # Mock successful query but no files created
            code_agent._query_claude = AsyncMock(
                return_value=Result.success("Some response without file creation")
            )
            
            result = await code_agent._execute_specific_task(test_task, task_context)
            
            assert result.is_failure()
            assert isinstance(result.get_error(), WorkspaceError)
            assert "did not create any files" in str(result.get_error())


class TestMetaAgentResultIntegration:
    """Test MetaAgent Result[T] integration."""
    
    @pytest.fixture
    def meta_agent(self):
        """Create a MetaAgent instance."""
        with patch('src.clients.openai_client.OpenAIClient'):
            return MetaAgent()
    
    @pytest.mark.asyncio
    async def test_process_request_returns_result_success(self, meta_agent):
        """Test process_request returns Result.success on successful execution."""
        # Mock the main methods to return successful Results
        meta_agent.decompose_request = AsyncMock(
            return_value=Result.success([
                Task(
                    id=uuid4(),
                    name="task1",
                    description="Test task",
                    agent_role=AgentRole.CORE_LOGIC,
                    priority=TaskPriority.MEDIUM,
                    status=TaskStatus.PENDING
                )
            ])
        )
        
        meta_agent.coordinate_execution = AsyncMock(
            return_value=Result.success({})
        )
        
        meta_agent.aggregate_results = AsyncMock(
            return_value=Result.success(ProjectResult(
                project_name="test_project",
                success=True,
                tasks_completed=1
            ))
        )
        
        result = await meta_agent.process_request("Create a test project")
        
        assert result.is_success()
        project_result = result.unwrap()
        assert isinstance(project_result, ProjectResult)
        assert project_result.success
        assert project_result.tasks_completed == 1
    
    @pytest.mark.asyncio
    async def test_process_request_propagates_decomposition_failure(self, meta_agent):
        """Test process_request propagates task decomposition failures."""
        # Mock decomposition failure
        error = TaskDecompositionError("Failed to decompose", agent_id=meta_agent.id)
        meta_agent.decompose_request = AsyncMock(
            return_value=Result.failure(error)
        )
        
        result = await meta_agent.process_request("Invalid request")
        
        assert result.is_failure()
        # The error should be the original TaskDecompositionError
        assert isinstance(result.get_error(), TaskDecompositionError)
        assert "Failed to decompose" in str(result.get_error())
    
    @pytest.mark.asyncio
    async def test_process_request_propagates_coordination_failure(self, meta_agent):
        """Test process_request propagates task coordination failures."""
        # Mock successful decomposition
        meta_agent.decompose_request = AsyncMock(
            return_value=Result.success([
                Task(
                    id=uuid4(),
                    name="task1",
                    description="Test task",
                    agent_role=AgentRole.CORE_LOGIC,
                    priority=TaskPriority.MEDIUM,
                    status=TaskStatus.PENDING
                )
            ])
        )
        
        # Mock coordination failure
        error = OrchestrationError("Coordination failed", agent_id=meta_agent.id)
        meta_agent.coordinate_execution = AsyncMock(
            return_value=Result.failure(error)
        )
        
        result = await meta_agent.process_request("Create project")
        
        assert result.is_failure()
        assert isinstance(result.get_error(), OrchestrationError)
    
    @pytest.mark.asyncio
    async def test_spawn_agents_returns_result_success(self, meta_agent, tmp_path):
        """Test spawn_agents returns Result.success with agent mapping."""
        tasks = [
            Task(
                id=uuid4(),
                name="code_task",
                description="Generate code",
                agent_role=AgentRole.CORE_LOGIC,
                priority=TaskPriority.MEDIUM,
                status=TaskStatus.PENDING
            ),
            Task(
                id=uuid4(),
                name="test_task",
                description="Generate tests",
                agent_role=AgentRole.TESTING,
                priority=TaskPriority.MEDIUM,
                status=TaskStatus.PENDING
            )
        ]
        
        # Create a task context
        context = TaskContext(
            project_root=tmp_path,
            shared_memory={},
            global_constraints={}
        )
        
        result = await meta_agent.spawn_agents(tasks, context)
        
        assert result.is_success()
        agents = result.unwrap()
        assert len(agents) == 2
        assert all(isinstance(agent_id, UUID) for agent_id in agents.keys())
    
    @pytest.mark.asyncio
    async def test_aggregate_results_handles_mixed_results(self, meta_agent):
        """Test aggregate_results handles mix of successful and failed tasks."""
        # Create mixed task results
        task_results = {
            uuid4(): MagicMock(success=True, artifacts=[uuid4()]),
            uuid4(): MagicMock(success=False, artifacts=[], errors=["Task failed"])
        }
        
        tasks = [
            Task(
                id=task_id,
                name=f"task_{i}",
                description="Test task",
                agent_role=AgentRole.CORE_LOGIC,
                priority=TaskPriority.MEDIUM,
                status=TaskStatus.COMPLETED
            )
            for i, task_id in enumerate(task_results.keys())
        ]
        
        result = await meta_agent.aggregate_results(task_results)
        
        assert result.is_success()
        project_result = result.unwrap()
        assert project_result.tasks_completed == 1
        assert project_result.tasks_failed == 1
        assert project_result.success_rate == 0.5


class TestResultErrorPropagation:
    """Test error propagation through Result[T] chains."""
    
    @pytest.mark.asyncio
    async def test_error_propagation_chain(self):
        """Test errors propagate correctly through async Result chains."""
        async def failing_operation() -> Result[str]:
            return Result.failure(CLIError("Operation failed"))
        
        async def dependent_operation(value: str) -> Result[str]:
            return Result.success(f"Processed: {value}")
        
        # Chain operations
        result = await failing_operation()
        
        if result.is_success():
            result = await dependent_operation(result.unwrap())
        
        assert result.is_failure()
        assert isinstance(result.get_error(), CLIError)
    
    def test_result_map_preserves_failure(self):
        """Test Result.map preserves failure state."""
        error = AgentResultError("Initial error")
        result: Result[str] = Result.failure(error)
        
        # Map should not execute on failure
        mapped_result = result.map(lambda x: x.upper())
        
        assert mapped_result.is_failure()
        assert mapped_result.get_error() == error
    
    def test_result_unwrap_or_provides_default(self):
        """Test Result.unwrap_or provides default on failure."""
        error = WorkspaceError("File not found")
        result: Result[str] = Result.failure(error)
        
        value = result.unwrap_or("default_value")
        
        assert value == "default_value"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])