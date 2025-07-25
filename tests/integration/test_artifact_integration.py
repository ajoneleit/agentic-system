"""Integration tests for artifact management system with agents."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.agents.meta_agent import MetaAgent
from src.agents.sub_agent import CodeGeneratorAgent, TestWriterAgent
from src.core.artifact_manager import ArtifactManager
from src.core.interfaces import (
    AgentRole,
    Artifact,
    ArtifactType,
    Task,
    TaskContext,
    TaskPriority,
)
from src.core.task_result import TaskResult


@pytest.fixture
async def artifact_manager(tmp_path):
    """Create an artifact manager instance."""
    manager = ArtifactManager(
        storage_path=tmp_path / "projects" / "test_project" / "artifacts",
        max_memory_cache_size=10,
        enable_compression=False,
    )
    await manager.initialize()
    yield manager
    # No cleanup method needed


@pytest.fixture
async def meta_agent(tmp_path):
    """Create a meta agent with mocked dependencies."""
    with patch("src.agents.meta_agent.ClaudeClient") as mock_claude:
        # Mock Claude client
        mock_claude_instance = AsyncMock()
        mock_claude.return_value = mock_claude_instance

        # Create meta agent
        agent = MetaAgent(artifact_storage_path=tmp_path / "projects")

        # Initialize with context
        context = TaskContext(
            project_root=tmp_path / "project",
            shared_memory={},
        )
        await agent.initialize(context)

        yield agent

        await agent.shutdown()


@pytest.mark.asyncio
async def test_sub_agent_creates_artifacts_with_artifact_manager(artifact_manager, tmp_path):
    """Test that sub-agents properly create and store artifacts when artifact manager is available."""
    # Create a code generator agent
    agent = CodeGeneratorAgent(uuid4())

    # Create task
    task = Task(
        name="Generate Calculator",
        description="Create a simple calculator module",
        priority=TaskPriority.HIGH,
        metadata={
            "specification": {
                "language": "python",
                "frameworks": [],
                "description": "Basic arithmetic calculator",
            }
        }
    )

    # Create context with artifact manager
    context = TaskContext(
        project_root=tmp_path / "project",
        artifact_manager=artifact_manager,
        project_id="test_project_123",
        artifact_naming_convention="{name}_{task_name}_{timestamp}",
        enable_artifact_caching=True,
    )

    # Mock Claude response and CLI availability
    with patch.object(agent, "_query_claude") as mock_query:
        from src.core.result import Result
        # Mock Claude response to indicate success (not JSON)
        mock_query.return_value = Result.success("Successfully created calculator.py with add and subtract functions.")

        # Mock ClaudeCodeClient to return True for check_cli_available
        with patch("src.agents.sub_agent.ClaudeCodeClient") as mock_cli_class:
            mock_cli_instance = AsyncMock()
            mock_cli_instance.check_cli_available = AsyncMock(return_value=True)
            mock_cli_class.return_value = mock_cli_instance

            # Initialize agent
            await agent.initialize(context)

            # Create the expected file that Claude would have created
            workspace_dir = context.project_root / "workspace"
            workspace_dir.mkdir(parents=True, exist_ok=True)
            calculator_file = workspace_dir / "calculator.py"
            calculator_file.write_text("def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n")

            # Execute task
            result = await agent.execute_task(task, context)

            # Verify result
            assert result.is_success()
            task_result = result.unwrap()
            assert isinstance(task_result, TaskResult)
            assert task_result.success
            assert len(task_result.artifacts) == 1
            assert task_result.primary_artifact is not None

            # Verify artifact was stored
            stored_artifact = await artifact_manager.get_artifact(task_result.primary_artifact)
            assert stored_artifact is not None
            assert stored_artifact.type == ArtifactType.SOURCE_CODE
            assert "def add(a, b):" in stored_artifact.content
            assert stored_artifact.metadata["project_id"] == "test_project_123"
            assert stored_artifact.metadata["agent_role"] == AgentRole.CORE_LOGIC.value


@pytest.mark.asyncio
async def test_test_writer_links_artifacts(artifact_manager, tmp_path):
    """Test that test writer properly links test artifacts to code artifacts."""
    # First create a code artifact
    code_artifact = Artifact(
        name="calculator.py",
        type=ArtifactType.SOURCE_CODE,
        content="def add(a, b): return a + b",
        path=Path("calculator.py"),
        language="python",
        task_id=uuid4(),
        agent_id=uuid4(),
    )
    stored_code = await artifact_manager.store_artifact(code_artifact)

    # Create test writer agent
    agent = TestWriterAgent(uuid4())

    # Create task
    task = Task(
        name="Write Calculator Tests",
        description="Create tests for calculator module",
        priority=TaskPriority.HIGH,
        metadata={
            "specification": {
                "language": "python",
                "test_framework": "pytest",
                "coverage_target": 90,
            },
            "code_artifact_id": str(stored_code.id),
            "code_to_test": code_artifact.content,
        }
    )

    # Create context with artifact manager
    context = TaskContext(
        project_root=tmp_path / "project",
        artifact_manager=artifact_manager,
        project_id="test_project_123",
        link_test_artifacts=True,
    )

    # Mock get_artifacts_by_task to return our code artifact
    async def mock_get_artifacts_by_task(task_id):
        # Return the code artifact when requested
        return [stored_code]

    artifact_manager.get_artifacts_by_task = mock_get_artifacts_by_task

    # Set up dependency tracker with proper mock
    from src.core.dependency_tracker import DependencyTracker
    tracker = DependencyTracker()
    tracker.add_dependency = AsyncMock()
    artifact_manager._dependency_tracker = tracker

    # Mock the CLI to have created test files
    test_file = context.project_root / "workspace" / "test_calculator.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_add():\\n    assert add(2, 3) == 5")

    # Mock Claude response (just a summary)
    with patch.object(agent, "_query_claude") as mock_query:
        from src.core.result import Result
        mock_query.return_value = Result.success("Created test_calculator.py with test cases for the add function.")

        # Mock ClaudeCodeClient to return True for check_cli_available
        with patch("src.agents.sub_agent.ClaudeCodeClient") as mock_cli_class:
            mock_cli_instance = AsyncMock()
            mock_cli_instance.check_cli_available = AsyncMock(return_value=True)
            mock_cli_class.return_value = mock_cli_instance

            # Initialize agent
            await agent.initialize(context)

            # Execute task
            result = await agent.execute_task(task, context)

            # Verify result
            assert result.is_success()
            task_result = result.unwrap()
            assert task_result.success
            assert len(task_result.artifacts) == 1

            # Verify artifact was stored
            test_artifact = await artifact_manager.get_artifact(task_result.primary_artifact)
            assert test_artifact is not None
            assert test_artifact.type == ArtifactType.TEST_CODE
            assert "def test_add():" in test_artifact.content
            assert test_artifact.metadata["tested_artifact_id"] == str(stored_code.id)

            # Verify dependency was tracked
            artifact_manager._dependency_tracker.add_dependency.assert_called_once()


@pytest.mark.asyncio
async def test_meta_agent_project_storage_integration(meta_agent, tmp_path):
    """Test that meta agent properly initializes project storage and passes artifact manager."""
    # Mock responses based on whether using OpenAI or Claude
    if meta_agent.using_openai:
        mock_create = patch.object(meta_agent.ai_client, "create_message")
    else:
        mock_create = patch.object(meta_agent.claude_client, "create_message")

    with mock_create as mock:
        # Setup responses for different calls
        if meta_agent.using_openai:
            responses = [
                # First call: generate project name
                {
                    "content": "project_test"
                },
                # Second call: task decomposition
                {
                    "content": '{"project_summary": "Calculator app", "tasks": [{"name": "Create Calculator", "description": "Build calculator", "complexity": "simple", "agent_type": "core_logic", "deliverable": "calculator.py", "dependencies": []}]}'
                }
            ]
        else:
            responses = [
                # First call: generate project name
                AsyncMock(
                    content=[
                        MagicMock(text='project_test')
                    ]
                ),
                # Second call: task decomposition
                AsyncMock(
                    content=[
                        MagicMock(
                            text='{"project_summary": "Calculator app", "tasks": [{"name": "Create Calculator", "description": "Build calculator", "complexity": "simple", "agent_type": "core_logic", "deliverable": "calculator.py", "dependencies": []}]}'
                        )
                    ]
                )
            ]
        mock.side_effect = responses

        # Mock coordinator to track context passed to agents
        captured_contexts = []

        async def mock_spawn_agent(role, context, metadata=None):
            captured_contexts.append(context)
            agent = AsyncMock()
            agent.id = uuid4()
            agent.role = role
            agent.execute_task = AsyncMock(
                return_value=TaskResult(
                    task_id=uuid4(),
                    agent_id=agent.id,
                    success=True,
                    artifacts=[uuid4()],
                )
            )
            return agent

        meta_agent.coordinator.spawn_agent = mock_spawn_agent

        # Process request
        result = await meta_agent.process_request("Create a simple calculator")

        # Verify project storage was initialized
        assert meta_agent._current_project_id is not None
        # Project ID should be descriptive, not just "project_"
        assert len(meta_agent._current_project_id) > 0

        # Verify project directory was created
        project_path = tmp_path / "projects" / meta_agent._current_project_id
        assert project_path.exists()
        assert (project_path / "project_metadata.json").exists()

        # Verify context passed to agents includes artifact manager
        assert len(captured_contexts) > 0
        agent_context = captured_contexts[0]
        assert agent_context.artifact_manager is not None
        assert agent_context.artifact_manager == meta_agent.artifact_manager
        assert agent_context.project_id == meta_agent._current_project_id
        assert agent_context.enable_artifact_caching is True
        assert agent_context.link_test_artifacts is True


@pytest.mark.asyncio
async def test_meta_agent_creates_project_manifest(meta_agent, tmp_path):
    """Test that meta agent creates a project manifest after execution."""
    # Create some task results
    task_results = {
        uuid4(): TaskResult(
            task_id=uuid4(),
            agent_id=uuid4(),
            success=True,
            artifacts=[uuid4(), uuid4()],
            execution_time=1.5,
        ),
        uuid4(): TaskResult(
            task_id=uuid4(),
            agent_id=uuid4(),
            success=False,
            artifacts=[],
            errors=["Compilation failed"],
            execution_time=0.5,
        ),
    }

    # Set up meta agent state
    meta_agent._current_project_id = "test_project_456"
    meta_agent._start_time = datetime.utcnow()
    meta_agent._active_project = {"project_summary": "Test project"}

    # Create manifest
    manifest = await meta_agent._create_project_manifest("Create calculator", task_results)

    # Verify manifest
    assert manifest is not None
    assert manifest.type == ArtifactType.DOCUMENTATION
    assert manifest.name == "test_project_456_manifest.json"
    assert manifest.metadata["is_manifest"] is True
    assert manifest.metadata["project_id"] == "test_project_456"

    # Verify manifest content
    import json
    manifest_data = json.loads(manifest.content)
    assert manifest_data["project_id"] == "test_project_456"
    assert manifest_data["request"] == "Create calculator"
    assert manifest_data["statistics"]["total_tasks"] == 2
    assert manifest_data["statistics"]["successful_tasks"] == 1
    assert manifest_data["statistics"]["failed_tasks"] == 1
    assert manifest_data["statistics"]["total_artifacts"] == 2


@pytest.mark.asyncio
async def test_artifact_update_creates_new_version(artifact_manager, tmp_path):
    """Test that updating artifacts through sub-agent creates new versions."""
    # Create a code generator agent
    agent = CodeGeneratorAgent(uuid4())

    # Create and store initial artifact
    initial_artifact = Artifact(
        name="calculator.py",
        type=ArtifactType.SOURCE_CODE,
        content="def add(a, b): return a + b",
        path=Path("calculator.py"),
        language="python",
        task_id=uuid4(),
        agent_id=agent.id,
    )
    stored = await artifact_manager.store_artifact(initial_artifact)

    # Create context
    context = TaskContext(
        project_root=tmp_path / "project",
        artifact_manager=artifact_manager,
        auto_version_on_change=True,
    )

    # Mock ClaudeCodeClient to return True for check_cli_available
    with patch("src.agents.sub_agent.ClaudeCodeClient") as mock_cli_class:
        mock_cli_instance = AsyncMock()
        mock_cli_instance.check_cli_available = AsyncMock(return_value=True)
        mock_cli_class.return_value = mock_cli_instance

        # Initialize agent
        await agent.initialize(context)

        # Update artifact
        updated = await agent._update_artifact(
            stored.id,
            "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b",
            "Added multiply function",
            context
        )

        # Verify update
        assert updated is not None
        assert updated.version == 2
        assert updated.previous_version_id == stored.id
        assert "def multiply(a, b):" in updated.content

        # Verify both versions exist
        v1 = await artifact_manager.get_artifact(stored.id, version=1)
        v2 = await artifact_manager.get_artifact(updated.id, version=2)
        assert v1 is not None
        assert v2 is not None
        assert v1.content != v2.content
