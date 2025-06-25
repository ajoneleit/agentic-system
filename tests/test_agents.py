"""Comprehensive tests for the agent system."""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

# Add parent directory to path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from anthropic.types import Message, Usage

from src.agents import (
    MetaAgent,
    ProjectResult,
    CodeGeneratorAgent,
    TestWriterAgent,
    DocumentationAgent,
    RefactorAgent,
    DebugAgent,
)
from src.core.exceptions import (
    AgentError,
    TaskDecompositionError,
    TaskExecutionError,
)
from src.core.interfaces import (
    AgentRole,
    Artifact,
    ArtifactType,
    Task,
    TaskContext,
    TaskPriority,
    TaskStatus,
)


class TestSubAgent:
    """Test SubAgent base class functionality."""
    
    @pytest.mark.asyncio
    async def test_sub_agent_initialization(self):
        """Test SubAgent initialization."""
        agent_id = uuid4()
        agent = CodeGeneratorAgent(agent_id)
        
        assert agent.id == agent_id
        assert agent.role == AgentRole.CORE_LOGIC
        assert agent.status == "idle"
        assert agent.current_task is None
        assert not agent._is_initialized
    
    @pytest.mark.asyncio
    async def test_sub_agent_initialize(self, task_context):
        """Test SubAgent context initialization."""
        agent = CodeGeneratorAgent(uuid4())
        
        with patch('src.agents.sub_agent.ClaudeClient'), \
             patch('src.agents.sub_agent.ClaudeCLIClient') as mock_cli:
            # Mock CLI as not available to force API usage
            mock_cli_instance = mock_cli.return_value
            mock_cli_instance.check_cli_available = AsyncMock(return_value=False)
            mock_cli_instance.close = AsyncMock()
            
            await agent.initialize(task_context)
            
            assert agent._is_initialized
            assert agent.context == task_context
            assert agent.claude_client is not None
            assert not agent.use_cli
    
    @pytest.mark.asyncio
    async def test_sub_agent_execute_task_not_initialized(self, sample_task, task_context):
        """Test executing task without initialization."""
        agent = CodeGeneratorAgent(uuid4())
        
        with pytest.raises(AgentError) as exc_info:
            await agent.execute_task(sample_task, task_context)
        
        assert "not initialized" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_sub_agent_execute_task_success(self, sample_task, task_context):
        """Test successful task execution."""
        agent = CodeGeneratorAgent(uuid4())
        
        with patch('src.agents.sub_agent.ClaudeClient'), \
             patch('src.agents.sub_agent.ClaudeCLIClient') as mock_cli:
            # Mock CLI as not available to force API usage
            mock_cli_instance = mock_cli.return_value
            mock_cli_instance.check_cli_available = AsyncMock(return_value=False)
            mock_cli_instance.close = AsyncMock()
            
            await agent.initialize(task_context)
            
            # Mock Claude response
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps({
                "code": "def hello(): return 'Hello, World!'",
                "filename": "hello.py",
                "dependencies": [],
                "notes": "Simple function",
                "complexity_score": 1,
            }))]
            
            agent.claude_client.create_message = AsyncMock(return_value=mock_response)
            
            # Execute task
            result = await agent.execute_task(sample_task, task_context)
            
            assert result.success
            assert len(result.artifacts) == 1
            assert result.primary_artifact is not None
            assert sample_task.id in agent.completed_tasks
    
    @pytest.mark.asyncio
    async def test_sub_agent_execute_task_failure(self, sample_task, task_context):
        """Test task execution failure."""
        agent = CodeGeneratorAgent(uuid4())
        
        with patch('src.agents.sub_agent.ClaudeClient'), \
             patch('src.agents.sub_agent.ClaudeCLIClient') as mock_cli:
            # Mock CLI as not available to force API usage
            mock_cli_instance = mock_cli.return_value
            mock_cli_instance.check_cli_available = AsyncMock(return_value=False)
            mock_cli_instance.close = AsyncMock()
            
            await agent.initialize(task_context)
            
            # Mock Claude to raise exception
            agent.claude_client.create_message = AsyncMock(
                side_effect=Exception("API Error")
            )
            
            # Execute task - should return failed result
            result = await agent.execute_task(sample_task, task_context)
            
            assert not result.success
            assert len(result.errors) > 0
            assert "API Error" in result.errors[0]
    
    @pytest.mark.asyncio
    async def test_sub_agent_collaboration(self, task_context):
        """Test agent collaboration handling."""
        agent = CodeGeneratorAgent(uuid4())
        
        with patch('src.agents.sub_agent.ClaudeClient'), \
             patch('src.agents.sub_agent.ClaudeCLIClient') as mock_cli:
            # Mock CLI as not available to force API usage
            mock_cli_instance = mock_cli.return_value
            mock_cli_instance.check_cli_available = AsyncMock(return_value=False)
            mock_cli_instance.close = AsyncMock()
            
            await agent.initialize(task_context)
            
            # Send collaboration message
            message = {
                "id": str(uuid4()),
                "sender_id": str(uuid4()),
                "receiver_id": str(agent.id),
                "message_type": "task_update",
                "subject": "Progress update",
                "content": {"progress": 50},
            }
            
            response = await agent.collaborate(None, message)
            
            assert response["acknowledged"]
            assert response["agent_id"] == str(agent.id)
            
            # Check message was queued
            assert agent._message_queue.qsize() > 0
    
    @pytest.mark.asyncio
    async def test_sub_agent_with_cli(self, sample_task, task_context):
        """Test SubAgent using CLI for code generation."""
        agent = CodeGeneratorAgent(uuid4())
        
        with patch('src.agents.sub_agent.ClaudeCLIClient') as mock_cli:
            # Mock CLI as available
            mock_cli_instance = mock_cli.return_value
            mock_cli_instance.check_cli_available = AsyncMock(return_value=True)
            mock_cli_instance.close = AsyncMock()
            mock_cli_instance.create_message_for_code = AsyncMock(return_value={
                "content": [{
                    "text": json.dumps({
                        "code": "def hello(): return 'Hello from CLI!'",
                        "filename": "hello_cli.py",
                        "dependencies": [],
                        "notes": "Generated via CLI",
                        "complexity_score": 1,
                    }),
                    "type": "text"
                }],
                "model": "claude-cli",
                "usage": {"input_tokens": 10, "output_tokens": 50}
            })
            
            await agent.initialize(task_context)
            
            # Verify CLI was chosen
            assert agent.use_cli
            assert agent.claude_cli_client is not None
            assert agent.claude_client is None
            
            # Execute task
            result = await agent.execute_task(sample_task, task_context)
            
            assert result.success
            assert len(result.artifacts) == 1
            
            # Verify CLI was called
            mock_cli_instance.create_message_for_code.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_sub_agent_shutdown(self, task_context):
        """Test agent shutdown."""
        agent = CodeGeneratorAgent(uuid4())
        
        with patch('src.agents.sub_agent.ClaudeClient'), \
             patch('src.agents.sub_agent.ClaudeCLIClient') as mock_cli:
            # Mock CLI as not available to force API usage
            mock_cli_instance = mock_cli.return_value
            mock_cli_instance.check_cli_available = AsyncMock(return_value=False)
            mock_cli_instance.close = AsyncMock()
            mock_cli_instance.close = AsyncMock()  # Add close method
            
            await agent.initialize(task_context)
            
            # Mock the claude client's close method
            agent.claude_client.close = AsyncMock()
            
            await agent.shutdown()
            
            assert agent.status == "terminated"
            assert agent._processing_task.cancelled()
            agent.claude_client.close.assert_called_once()


class TestSpecializedAgents:
    """Test specialized agent implementations."""
    
    @pytest.fixture
    def mock_cli_unavailable(self):
        """Mock CLI as unavailable to force API usage."""
        with patch('src.agents.sub_agent.ClaudeCLIClient') as mock_cli:
            mock_cli_instance = mock_cli.return_value
            mock_cli_instance.check_cli_available = AsyncMock(return_value=False)
            mock_cli_instance.close = AsyncMock()
            yield mock_cli_instance
    
    @pytest.mark.asyncio
    async def test_code_generator_agent(self, task_context, mock_cli_unavailable):
        """Test CodeGeneratorAgent specific functionality."""
        agent = CodeGeneratorAgent(uuid4())
        
        task = Task(
            name="Generate Calculator",
            description="Create a calculator class",
            metadata={
                "specification": {
                    "language": "python",
                    "frameworks": [],
                }
            }
        )
        
        with patch('src.agents.sub_agent.ClaudeClient'):
            await agent.initialize(task_context)
            
            # Mock Claude response
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps({
                "code": "class Calculator:\n    pass",
                "filename": "calculator.py",
                "dependencies": [],
                "complexity_score": 3,
            }))]
            
            agent.claude_client.create_message = AsyncMock(return_value=mock_response)
            
            artifacts = await agent._execute_specific_task(task, task_context)
            
            assert len(artifacts) == 1
            assert artifacts[0].type == ArtifactType.SOURCE_CODE
            assert artifacts[0].language == "python"
            assert "Calculator" in artifacts[0].content
    
    @pytest.mark.asyncio
    async def test_test_writer_agent(self, task_context, mock_cli_unavailable):
        """Test TestWriterAgent specific functionality."""
        agent = TestWriterAgent(uuid4())
        
        task = Task(
            name="Write Tests",
            description="Create unit tests",
            metadata={
                "code_to_test": "def add(a, b): return a + b",
                "code_artifact_id": str(uuid4()),  # Add required artifact ID
                "specification": {
                    "test_framework": "pytest",
                    "coverage_target": 100,
                }
            }
        )
        
        with patch('src.agents.sub_agent.ClaudeClient'):
            await agent.initialize(task_context)
            
            # Mock Claude response
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps({
                "test_code": "def test_add():\n    assert add(2, 3) == 5",
                "filename": "test_calculator.py",
                "test_cases": [{"name": "test_add", "type": "unit"}],
                "coverage_estimate": 100,
            }))]
            
            agent.claude_client.create_message = AsyncMock(return_value=mock_response)
            
            artifacts = await agent._execute_specific_task(task, task_context)
            
            assert len(artifacts) == 1
            assert artifacts[0].type == ArtifactType.TEST_CODE
            assert "test_add" in artifacts[0].content
    
    @pytest.mark.asyncio
    async def test_documentation_agent(self, task_context, mock_cli_unavailable):
        """Test DocumentationAgent specific functionality."""
        agent = DocumentationAgent(uuid4())
        
        task = Task(
            name="Document Code",
            description="Create API documentation",
            metadata={
                "code_to_document": "class Example: pass",
                "specification": {
                    "doc_type": "api",
                    "target_audience": "developers",
                }
            }
        )
        
        with patch('src.agents.sub_agent.ClaudeClient'):
            await agent.initialize(task_context)
            
            # Mock Claude response
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps({
                "documentation": "# Example API\n\nDocumentation here",
                "sections": [{"title": "Overview", "content": "..."}],
            }))]
            
            agent.claude_client.create_message = AsyncMock(return_value=mock_response)
            
            artifacts = await agent._execute_specific_task(task, task_context)
            
            assert len(artifacts) == 1
            assert artifacts[0].type == ArtifactType.DOCUMENTATION
            assert artifacts[0].language == "markdown"


class TestMetaAgent:
    """Test MetaAgent functionality."""
    
    @pytest.fixture
    def meta_agent(self):
        """Create MetaAgent instance with mocked dependencies."""
        with patch('src.agents.meta_agent.ClaudeClient'), \
             patch('src.agents.meta_agent.TaskManager'), \
             patch('src.agents.meta_agent.CommunicationHub'), \
             patch('src.agents.meta_agent.AgentCoordinator'):
            agent = MetaAgent()
            yield agent
    
    @pytest.mark.asyncio
    async def test_meta_agent_initialization(self, meta_agent):
        """Test MetaAgent initialization."""
        assert meta_agent.role == AgentRole.META
        assert meta_agent.claude_client is not None
        assert meta_agent.task_manager is not None
        assert meta_agent.communication_hub is not None
        assert meta_agent.coordinator is not None
    
    @pytest.mark.asyncio
    async def test_decompose_task_success(self, meta_agent):
        """Test successful task decomposition."""
        user_request = "Create a web API for managing todos"
        
        # Mock Claude response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "project_summary": "Todo API project",
            "tasks": [
                {
                    "name": "Create API endpoints",
                    "description": "Implement REST endpoints",
                    "deliverable": "API code",
                    "dependencies": [],
                    "complexity": "medium",
                    "agent_type": "core_logic",
                    "estimated_time_minutes": 30,
                    "requirements": {"language": "python"},
                },
                {
                    "name": "Write tests",
                    "description": "Create unit tests",
                    "deliverable": "Test suite",
                    "dependencies": ["Create API endpoints"],
                    "complexity": "simple",
                    "agent_type": "testing",
                    "estimated_time_minutes": 20,
                    "requirements": {},
                }
            ],
            "execution_strategy": {
                "parallel_groups": [["Create API endpoints"], ["Write tests"]],
                "critical_path": ["Create API endpoints", "Write tests"],
                "estimated_total_time_minutes": 50,
            }
        }))]
        
        meta_agent.claude_client.create_message = AsyncMock(return_value=mock_response)
        
        tasks = await meta_agent.decompose_task(user_request)
        
        assert len(tasks) == 2
        assert tasks[0].name == "Create API endpoints"
        assert tasks[0].priority == TaskPriority.MEDIUM
        assert tasks[0].required_role == AgentRole.CORE_LOGIC
        
        assert tasks[1].name == "Write tests"
        assert len(tasks[1].dependencies) == 1
        assert tasks[1].dependencies[0] == tasks[0].id
    
    @pytest.mark.asyncio
    async def test_decompose_task_failure(self, meta_agent):
        """Test task decomposition failure."""
        user_request = "Invalid request"
        
        # Mock Claude to return invalid JSON
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Invalid JSON")]
        
        meta_agent.claude_client.create_message = AsyncMock(return_value=mock_response)
        
        with pytest.raises(TaskDecompositionError) as exc_info:
            await meta_agent.decompose_task(user_request)
        
        assert exc_info.value.user_prompt == user_request
    
    @pytest.mark.asyncio
    async def test_process_request_simple(self, meta_agent, task_context):
        """Test processing a simple user request."""
        user_request = "Create a hello world function"
        
        # Mock task decomposition
        mock_task = Task(
            name="Create function",
            description="Create hello world function",
            priority=TaskPriority.LOW,
            required_role=AgentRole.CORE_LOGIC,
        )
        
        meta_agent.decompose_task = AsyncMock(return_value=[mock_task])
        meta_agent.task_manager.add_tasks = AsyncMock()
        meta_agent.task_manager.get_next_tasks = AsyncMock(
            side_effect=[[mock_task], []]  # Return task once, then empty
        )
        
        # Mock task completion - update task status when complete_task is called
        async def mock_complete_task(task_id, artifact_ids):
            if task_id == mock_task.id:
                mock_task.status = TaskStatus.COMPLETED
                mock_task.artifacts = artifact_ids
        
        meta_agent.task_manager.complete_task = AsyncMock(side_effect=mock_complete_task)
        meta_agent.task_manager._queue.get_all_tasks = AsyncMock(return_value=[mock_task])
        meta_agent.task_manager.get_blocked_tasks = AsyncMock(return_value=[])
        meta_agent.task_manager.fail_task = AsyncMock()
        meta_agent.task_manager.get_critical_path = AsyncMock(return_value=[])
        
        # Mock agent spawning and execution
        mock_agent = MagicMock()
        mock_agent.id = uuid4()
        
        # Import TaskResult
        from src.core.task_result import TaskResult
        
        # Mock execute_task to return a TaskResult
        mock_agent.execute_task = AsyncMock(return_value=TaskResult(
            task_id=mock_task.id,
            agent_id=mock_agent.id,
            success=True,
            artifacts=[uuid4()],
            execution_time=10.0
        ))
        
        meta_agent.coordinator.spawn_agent = AsyncMock(return_value=mock_agent)
        meta_agent.coordinator.assign_task = AsyncMock()
        meta_agent.coordinator.handle_task_completion = AsyncMock()
        meta_agent.coordinator.terminate_agent = AsyncMock()
        
        meta_agent.task_manager.start_task = AsyncMock()
        meta_agent.task_manager.get_progress = AsyncMock(return_value={
            "completed_tasks": 1,
            "total_tasks": 1,
        })
        
        # Mock context
        meta_agent.context = task_context
        
        # Mock project storage initialization
        meta_agent._initialize_project_storage = AsyncMock(return_value="test_project_123")
        meta_agent._store_execution_artifacts = AsyncMock()
        meta_agent._create_project_manifest = AsyncMock(return_value=None)
        
        # Mock Claude client for assign_task
        mock_claude_response = MagicMock()
        mock_claude_response.content = [MagicMock(text=json.dumps({
            "specification": "Detailed task specification",
            "requirements": ["Python 3.8+"],
            "approach": "Create a simple function"
        }))]
        meta_agent.claude_client.create_message = AsyncMock(return_value=mock_claude_response)
        
        # Process request
        result = await meta_agent.process_request(user_request)
        
        assert isinstance(result, ProjectResult)
        assert result.tasks_completed == 1
        assert result.tasks_failed == 0
        assert result.success_rate == 1.0
    
    @pytest.mark.asyncio
    async def test_handle_failure(self, meta_agent):
        """Test handling task failure."""
        failed_task = Task(
            name="Failed task",
            description="This task failed",
            metadata={"some": "data"},
        )
        error = "Compilation error"
        
        # Mock Claude response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "failure_analysis": "Code syntax error",
            "repair_tasks": [
                {
                    "name": "Fix syntax",
                    "description": "Fix the syntax error",
                    "agent_type": "debugging",
                    "priority": "high",
                }
            ]
        }))]
        
        meta_agent.claude_client.create_message = AsyncMock(return_value=mock_response)
        meta_agent.task_manager.add_tasks = AsyncMock()
        
        repair_tasks = await meta_agent.handle_failure(failed_task, error)
        
        assert len(repair_tasks) == 1
        assert repair_tasks[0].name == "Repair: Fix syntax"
        assert repair_tasks[0].priority == TaskPriority.HIGH
        assert failed_task.id in repair_tasks[0].dependencies
        assert repair_tasks[0].metadata["is_repair"]
    
    @pytest.mark.asyncio
    async def test_monitor_progress(self, meta_agent):
        """Test progress monitoring."""
        # Mock data
        meta_agent._active_project = {"project_summary": "Test project"}
        
        meta_agent.task_manager.get_progress = AsyncMock(return_value={
            "total_tasks": 5,
            "completed_tasks": 3,
            "active_tasks": 1,
            "failed_tasks": 1,
        })
        
        meta_agent.coordinator.get_system_status = AsyncMock(return_value={
            "total_agents": 2,
            "agent_status_breakdown": {"working": 1, "idle": 1},
        })
        
        meta_agent.task_manager._queue.get_all_tasks = AsyncMock(return_value=[])
        
        # Mock Claude response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "overall_progress": {"completion_percentage": 60},
        }))]
        
        meta_agent.claude_client.create_message = AsyncMock(return_value=mock_response)
        
        progress = await meta_agent.monitor_progress()
        
        assert "task_progress" in progress
        assert "system_status" in progress
        assert "aggregated_analysis" in progress
        assert progress["task_progress"]["completed_tasks"] == 3


class TestIntegration:
    """Integration tests for the agent system."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_simple_code_generation_flow(self, tmp_path):
        """Test a simple code generation flow end-to-end."""
        # This test would require actual API keys and would make real calls
        # For unit testing, we skip this
        #pytest.skip("Integration test equires APIr keys")