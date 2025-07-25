"""Tests for refactored components.

This module tests the new refactored components to ensure they work correctly.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from src.agents.artifact_factory import ArtifactFactory
from src.agents.execution_coordinator import ExecutionCoordinator
from src.agents.meta_agent_config import MetaAgentConfig
from src.agents.project_manager import ProjectManager
from src.agents.task_decomposer import TaskDecomposer
from src.clients.temp_file_manager import TempFileManager
from src.core.interfaces import ArtifactType, Task, TaskContext, TaskPriority, TaskStatus
from src.core.result import Result
from src.core.task_result import TaskResult


class TestTaskDecomposer:
    """Tests for TaskDecomposer class."""

    @pytest.fixture
    def mock_openai_client(self):
        """Mock OpenAI client."""
        client = Mock()
        client.create_chat_completion = AsyncMock()
        return client

    @pytest.fixture
    def task_decomposer(self, mock_openai_client):
        """Create TaskDecomposer instance."""
        return TaskDecomposer(mock_openai_client)

    @pytest.mark.asyncio
    async def test_decompose_request_success(self, task_decomposer, mock_openai_client):
        """Test successful task decomposition."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '''
        {
            "tasks": [
                {
                    "name": "create_calculator",
                    "description": "Create a calculator class",
                    "type": "code_generation",
                    "priority": "high",
                    "dependencies": []
                }
            ],
            "dependencies": {},
            "complexity_analysis": {"overall": "medium"}
        }
        '''
        mock_openai_client.create_chat_completion.return_value = mock_response

        # Test decomposition
        result = await task_decomposer.decompose_request("Create a calculator", "test_project")

        assert result.is_success()
        tasks = result.value
        assert len(tasks) == 1
        assert tasks[0].name == "create_calculator"
        assert tasks[0].type == "code_generation"
        assert tasks[0].priority == TaskPriority.HIGH

    @pytest.mark.asyncio
    async def test_decompose_request_caching(self, task_decomposer, mock_openai_client):
        """Test that decomposition results are cached."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '''
        {
            "tasks": [{"name": "test", "description": "test", "type": "general", "priority": "medium", "dependencies": []}],
            "dependencies": {},
            "complexity_analysis": {"overall": "low"}
        }
        '''
        mock_openai_client.create_chat_completion.return_value = mock_response

        # First call
        result1 = await task_decomposer.decompose_request("test request", "test_project")
        assert result1.is_success()
        assert mock_openai_client.create_chat_completion.call_count == 1

        # Second call should use cache
        result2 = await task_decomposer.decompose_request("test request", "test_project")
        assert result2.is_success()
        assert mock_openai_client.create_chat_completion.call_count == 1  # No additional call

    def test_validate_dependencies_success(self, task_decomposer):
        """Test successful dependency validation."""
        dependencies = {
            "task_a": ["task_b"],
            "task_b": [],
            "task_c": ["task_b"]
        }

        result = asyncio.run(task_decomposer.validate_dependencies(dependencies))
        assert result is True

    def test_validate_dependencies_circular(self, task_decomposer):
        """Test circular dependency detection."""
        dependencies = {
            "task_a": ["task_b"],
            "task_b": ["task_c"],
            "task_c": ["task_a"]
        }

        result = asyncio.run(task_decomposer.validate_dependencies(dependencies))
        assert result is False


class TestProjectManager:
    """Tests for ProjectManager class."""

    @pytest.fixture
    def temp_storage(self, tmp_path):
        """Create temporary storage directory."""
        return tmp_path / "test_storage"

    @pytest.fixture
    def project_manager(self, temp_storage):
        """Create ProjectManager instance."""
        return ProjectManager(temp_storage)

    @pytest.mark.asyncio
    async def test_initialize_project_storage(self, project_manager, temp_storage):
        """Test project storage initialization."""
        user_request = "Create a simple calculator"

        result = await project_manager.initialize_project_storage(user_request)

        assert result.is_success()
        project_id = result.value
        assert project_id

        # Check that directories were created
        project_path = temp_storage / "projects" / project_id
        assert project_path.exists()
        assert (project_path / "workspace").exists()
        assert (project_path / "artifacts").exists()
        assert (project_path / "project_metadata.json").exists()

    @pytest.mark.asyncio
    async def test_get_project_info(self, project_manager):
        """Test getting project information."""
        # First create a project
        create_result = await project_manager.initialize_project_storage("Test project")
        assert create_result.is_success()
        project_id = create_result.value

        # Get project info
        info_result = await project_manager.get_project_info(project_id)
        assert info_result.is_success()

        project_info = info_result.value
        assert project_info["id"] == project_id
        assert project_info["request"] == "Test project"
        assert project_info["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_list_projects(self, project_manager):
        """Test listing projects."""
        # Create some projects
        await project_manager.initialize_project_storage("Project 1")
        await project_manager.initialize_project_storage("Project 2")

        # List projects
        result = await project_manager.list_projects()
        assert result.is_success()

        projects = result.value
        assert len(projects) == 2
        assert any(p["request"] == "Project 1" for p in projects)
        assert any(p["request"] == "Project 2" for p in projects)


class TestExecutionCoordinator:
    """Tests for ExecutionCoordinator class."""

    @pytest.fixture
    def execution_coordinator(self):
        """Create ExecutionCoordinator instance."""
        return ExecutionCoordinator(max_parallel_tasks=2, task_timeout=30)

    @pytest.fixture
    def mock_task_context(self, tmp_path):
        """Create mock task context."""
        return TaskContext(
            project_root=tmp_path,
            shared_memory={},
            parent_task_id=None,
            sibling_task_ids=set(),
            artifact_manager=Mock(),
            project_id="test_project"
        )

    @pytest.mark.asyncio
    async def test_coordinate_execution_success(self, execution_coordinator, mock_task_context):
        """Test successful task coordination."""
        # Create test tasks
        task1 = Task(
            id=uuid4(),
            project_id="test_project",
            name="task1",
            description="Test task 1",
            type="general",
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.PENDING,
            dependencies=[]
        )

        task2 = Task(
            id=uuid4(),
            project_id="test_project",
            name="task2",
            description="Test task 2",
            type="general",
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.PENDING,
            dependencies=[]
        )

        tasks = [task1, task2]

        # Mock agent execution
        with patch('src.agents.execution_coordinator.SubAgent') as mock_agent_class:
            mock_agent = Mock()
            mock_agent.execute_task = AsyncMock(return_value=TaskResult(
                success=True,
                artifacts=[],
                execution_time=1.0
            ))
            mock_agent.initialize = AsyncMock(return_value=Result.success(None))
            mock_agent.id = uuid4()
            mock_agent.role = Mock()
            mock_agent_class.return_value = mock_agent

            # Execute tasks
            result = await execution_coordinator.coordinate_execution(tasks, mock_task_context)

            assert result.is_success()
            task_results = result.value
            assert len(task_results) == 2
            assert all(result.success for result in task_results.values())

    def test_get_execution_stats(self, execution_coordinator):
        """Test getting execution statistics."""
        stats = execution_coordinator.get_execution_stats()

        assert 'total_tasks' in stats
        assert 'successful_tasks' in stats
        assert 'failed_tasks' in stats
        assert 'total_execution_time' in stats

        # Initial stats should be zero
        assert stats['total_tasks'] == 0
        assert stats['successful_tasks'] == 0
        assert stats['failed_tasks'] == 0
        assert stats['total_execution_time'] == 0.0


class TestArtifactFactory:
    """Tests for ArtifactFactory class."""

    @pytest.fixture
    def artifact_factory(self, tmp_path):
        """Create ArtifactFactory instance."""
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()
        return ArtifactFactory("test_project", workspace_path)

    @pytest.fixture
    def mock_task(self):
        """Create mock task."""
        return Task(
            id=uuid4(),
            project_id="test_project",
            name="test_task",
            description="Test task",
            type="general",
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.PENDING,
            dependencies=[]
        )

    def test_create_code_artifact(self, artifact_factory, mock_task):
        """Test creating code artifact."""
        code_content = "def hello():\n    print('Hello, World!')"

        result = artifact_factory.create_code_artifact(
            content=code_content,
            filename="hello.py",
            task=mock_task,
            language="python"
        )

        assert result.is_success()
        artifact = result.value
        assert artifact.name == "hello.py"
        assert artifact.type == ArtifactType.SOURCE_CODE
        assert artifact.content == code_content
        assert artifact.metadata["language"] == "python"
        assert artifact.metadata["task_id"] == str(mock_task.id)

    def test_create_test_artifact(self, artifact_factory, mock_task):
        """Test creating test artifact."""
        test_content = "def test_hello():\n    assert hello() == 'Hello, World!'"

        result = artifact_factory.create_test_artifact(
            content=test_content,
            filename="test_hello.py",
            task=mock_task,
            test_framework="pytest"
        )

        assert result.is_success()
        artifact = result.value
        assert artifact.name == "test_hello.py"
        assert artifact.type == ArtifactType.TEST_CODE
        assert artifact.content == test_content
        assert artifact.metadata["test_framework"] == "pytest"

    def test_create_documentation_artifact(self, artifact_factory, mock_task):
        """Test creating documentation artifact."""
        doc_content = "# Hello Function\n\nThis function prints hello world."

        result = artifact_factory.create_documentation_artifact(
            content=doc_content,
            filename="hello_docs.md",
            task=mock_task,
            doc_type="markdown"
        )

        assert result.is_success()
        artifact = result.value
        assert artifact.name == "hello_docs.md"
        assert artifact.type == ArtifactType.DOCUMENTATION
        assert artifact.content == doc_content
        assert artifact.metadata["doc_type"] == "markdown"


class TestMetaAgentConfig:
    """Tests for MetaAgentConfig class."""

    def test_default_config(self):
        """Test default configuration."""
        config = MetaAgentConfig()

        assert config.task_execution.max_parallel_tasks == 3
        assert config.task_execution.task_timeout == 300
        assert config.retry.max_retries == 3
        assert config.enable_caching is True
        assert config.openai_model == "gpt-4"

    def test_config_validation_success(self):
        """Test successful config validation."""
        config = MetaAgentConfig()
        config.openai_api_key = "test_key"
        config.anthropic_api_key = "test_key"

        errors = config.validate()
        # May have path-related errors, but no key errors
        assert not any("API key" in error for error in errors)

    def test_config_validation_missing_keys(self):
        """Test config validation with missing API keys."""
        config = MetaAgentConfig()

        errors = config.validate()
        assert any("OpenAI API key" in error for error in errors)
        assert any("Anthropic API key" in error for error in errors)

    def test_config_to_dict(self):
        """Test config serialization to dict."""
        config = MetaAgentConfig()
        config.openai_api_key = "test_key"
        config.anthropic_api_key = "test_key"

        config_dict = config.to_dict()

        assert "retry" in config_dict
        assert "task_execution" in config_dict
        assert "project" in config_dict
        assert config_dict["retry"]["max_retries"] == 3
        assert config_dict["task_execution"]["max_parallel_tasks"] == 3


class TestTempFileManager:
    """Tests for TempFileManager class."""

    @pytest.fixture
    def temp_manager(self):
        """Create TempFileManager instance."""
        return TempFileManager(cleanup_on_exit=False)

    def test_create_temp_file(self, temp_manager):
        """Test temporary file creation."""
        content = "This is test content"

        result = temp_manager.create_temp_file(content)

        assert result.is_success()
        temp_path = result.value
        assert temp_path.exists()
        assert temp_path.read_text() == content

        # Clean up
        temp_manager.cleanup_file(temp_path)

    def test_temp_file_context_manager(self, temp_manager):
        """Test temporary file context manager."""
        content = "Context manager test"

        with temp_manager.temp_file_context(content) as temp_path:
            assert temp_path.exists()
            assert temp_path.read_text() == content

        # File should be cleaned up after context
        assert not temp_path.exists()

    def test_cleanup_all_files(self, temp_manager):
        """Test cleaning up all files."""
        # Create multiple temp files
        result1 = temp_manager.create_temp_file("Content 1")
        result2 = temp_manager.create_temp_file("Content 2")

        assert result1.is_success()
        assert result2.is_success()

        temp_path1 = result1.value
        temp_path2 = result2.value

        assert temp_path1.exists()
        assert temp_path2.exists()
        assert temp_manager.get_temp_file_count() == 2

        # Clean up all
        temp_manager.cleanup_all()

        assert not temp_path1.exists()
        assert not temp_path2.exists()
        assert temp_manager.get_temp_file_count() == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
