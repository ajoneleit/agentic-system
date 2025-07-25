"""Test configuration and fixtures for the Agentic Coding System.

This module provides pytest fixtures and configuration for testing,
including mocks, test data generators, and async support.
"""

import asyncio
import sys
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
import pytest_asyncio
from aioresponses import aioresponses
from anthropic.types import Message, Usage
from pydantic import SecretStr

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    AgentSettings,
    APISettings,
    ClaudeModel,
    Environment,
    Settings,
)
from src.core.interfaces import (
    Agent,
    AgentRole,
    Artifact,
    ArtifactType,
    Task,
    TaskContext,
    TaskPriority,
    TaskStatus,
)


# Test configuration
@pytest.fixture
def test_settings() -> Settings:
    """Provide test settings instance."""
    return Settings(
        environment=Environment.TESTING,
        debug=True,
        api=APISettings(
            key=SecretStr("test-api-key"),
            base_url="http://test-api.example.com",
            timeout=30,
            max_retries=2,
            rate_limit_per_minute=100,
        ),
        agent=AgentSettings(
            max_parallel_agents=5,
            default_model=ClaudeModel.HAIKU,
            meta_agent_model=ClaudeModel.SONNET,
            verification_timeout=60,
            max_repair_attempts=3,
        ),
    )


# Mock fixtures
@pytest.fixture
def mock_claude_client():
    """Mock Claude API client."""
    client = MagicMock()
    client.create_message = AsyncMock()
    client.stream_message = AsyncMock()
    client.get_metrics = Mock(return_value={
        "total_requests": 10,
        "total_tokens_used": 1000,
        "average_tokens_per_request": 100,
    })
    return client


@pytest.fixture
def mock_claude_response() -> Message:
    """Mock Claude API response."""
    return Message(
        id="msg_test123",
        type="message",
        role="assistant",
        content=[{"type": "text", "text": "Test response"}],
        model=ClaudeModel.SONNET.value,
        stop_reason="end_turn",
        stop_sequence=None,
        usage=Usage(input_tokens=50, output_tokens=20),
    )


@pytest.fixture
def aiohttp_mock():
    """Mock aiohttp requests."""
    with aioresponses() as m:
        yield m


# Test data generators
@pytest.fixture
def sample_task() -> Task:
    """Generate a sample task."""
    return Task(
        id=uuid4(),
        name="Test Task",
        description="A test task for unit testing",
        status=TaskStatus.PENDING,
        priority=TaskPriority.MEDIUM,
        dependencies=[],
        required_role=AgentRole.CORE_LOGIC,
        estimated_complexity="medium",
        metadata={"test": True},
    )


@pytest.fixture
def sample_tasks() -> List[Task]:
    """Generate multiple sample tasks with dependencies."""
    task1 = Task(
        id=uuid4(),
        name="Setup Environment",
        description="Initialize the development environment",
        status=TaskStatus.COMPLETED,
        priority=TaskPriority.HIGH,
    )

    task2 = Task(
        id=uuid4(),
        name="Implement Core Logic",
        description="Write the main business logic",
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.HIGH,
        dependencies=[task1.id],
    )

    task3 = Task(
        id=uuid4(),
        name="Write Tests",
        description="Create unit tests for core logic",
        status=TaskStatus.PENDING,
        priority=TaskPriority.MEDIUM,
        dependencies=[task2.id],
        required_role=AgentRole.TESTING,
    )

    task4 = Task(
        id=uuid4(),
        name="Generate Documentation",
        description="Create API documentation",
        status=TaskStatus.PENDING,
        priority=TaskPriority.LOW,
        dependencies=[task2.id],
        required_role=AgentRole.DOCUMENTATION,
    )

    return [task1, task2, task3, task4]


@pytest.fixture
def sample_artifact() -> Artifact:
    """Generate a sample artifact."""
    return Artifact(
        id=uuid4(),
        type=ArtifactType.SOURCE_CODE,
        name="main.py",
        path=Path("src/main.py"),
        content='def hello_world():\n    return "Hello, World!"\n',
        language="python",
        task_id=uuid4(),
        agent_id=uuid4(),
        size_bytes=50,
        compilation_status=True,
        test_coverage=100.0,
        quality_score=0.95,
    )


@pytest.fixture
def sample_artifacts() -> List[Artifact]:
    """Generate multiple sample artifacts."""
    task_id = uuid4()
    agent_id = uuid4()

    source_artifact = Artifact(
        id=uuid4(),
        type=ArtifactType.SOURCE_CODE,
        name="calculator.py",
        path=Path("src/calculator.py"),
        content='''class Calculator:
    def add(self, a: int, b: int) -> int:
        return a + b
    
    def subtract(self, a: int, b: int) -> int:
        return a - b
''',
        language="python",
        task_id=task_id,
        agent_id=agent_id,
    )

    test_artifact = Artifact(
        id=uuid4(),
        type=ArtifactType.TEST_CODE,
        name="test_calculator.py",
        path=Path("tests/test_calculator.py"),
        content='''import pytest
from src.calculator import Calculator

def test_add():
    calc = Calculator()
    assert calc.add(2, 3) == 5

def test_subtract():
    calc = Calculator()
    assert calc.subtract(5, 3) == 2
''',
        language="python",
        task_id=task_id,
        agent_id=agent_id,
        dependencies=[source_artifact.id],
    )

    return [source_artifact, test_artifact]


@pytest.fixture
def task_context(tmp_path: Path) -> TaskContext:
    """Generate a sample task context."""
    return TaskContext(
        project_root=tmp_path,
        shared_memory={"test_key": "test_value"},
        parent_task_id=uuid4(),
        sibling_task_ids={uuid4(), uuid4()},
        global_constraints={"max_tokens": 1000},
        execution_metadata={"start_time": datetime.utcnow()},
    )


# Async fixtures
@pytest_asyncio.fixture
async def mock_agent() -> AsyncGenerator[Agent, None]:
    """Mock agent instance."""
    agent = MagicMock(spec=Agent)
    agent.id = uuid4()
    agent.role = AgentRole.CORE_LOGIC
    agent.status = "idle"
    agent.initialize = AsyncMock()
    agent.execute_task = AsyncMock()
    agent.collaborate = AsyncMock()
    agent.shutdown = AsyncMock()
    agent.report_status = AsyncMock(return_value={
        "id": str(agent.id),
        "role": agent.role.value,
        "status": agent.status,
        "completed_tasks": 0,
    })

    yield agent

    # Cleanup
    await agent.shutdown()


# Event loop configuration
@pytest.fixture(scope="session")
def event_loop_policy():
    """Set event loop policy for Windows compatibility."""
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.get_event_loop_policy()


# Test utilities
class TestDataGenerator:
    """Generate test data for various scenarios."""

    @staticmethod
    def create_task(
        name: str = "Test Task",
        status: TaskStatus = TaskStatus.PENDING,
        **kwargs: Any,
    ) -> Task:
        """Create a task with custom attributes."""
        defaults = {
            "id": uuid4(),
            "description": f"Description for {name}",
            "priority": TaskPriority.MEDIUM,
            "dependencies": [],
            "created_at": datetime.utcnow(),
        }
        defaults.update(kwargs)
        return Task(name=name, status=status, **defaults)

    @staticmethod
    def create_artifact(
        name: str = "test.py",
        content: str = "# Test content",
        artifact_type: ArtifactType = ArtifactType.SOURCE_CODE,
        **kwargs: Any,
    ) -> Artifact:
        """Create an artifact with custom attributes."""
        defaults = {
            "id": uuid4(),
            "path": Path(f"src/{name}"),
            "task_id": uuid4(),
            "agent_id": uuid4(),
            "size_bytes": len(content),
            "created_at": datetime.utcnow(),
        }
        defaults.update(kwargs)
        return Artifact(
            name=name,
            content=content,
            type=artifact_type,
            **defaults,
        )

    @staticmethod
    def create_message_response(
        content: str = "Test response",
        model: str = ClaudeModel.SONNET.value,
        input_tokens: int = 100,
        output_tokens: int = 50,
    ) -> Message:
        """Create a mock Claude message response."""
        return Message(
            id=f"msg_{uuid4().hex[:8]}",
            type="message",
            role="assistant",
            content=[{"type": "text", "text": content}],
            model=model,
            stop_reason="end_turn",
            stop_sequence=None,
            usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
        )


@pytest.fixture
def test_data_generator() -> TestDataGenerator:
    """Provide test data generator instance."""
    return TestDataGenerator()


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests"
    )
    config.addinivalue_line(
        "markers", "slow: Slow tests"
    )
    config.addinivalue_line(
        "markers", "requires_api_key: Tests requiring real API key"
    )


# Test environment setup
@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch, tmp_path):
    """Set up test environment variables."""
    monkeypatch.setenv("ACS_ENVIRONMENT", "testing")
    monkeypatch.setenv("ACS_API__KEY", "test-api-key")
    monkeypatch.setenv("ACS_DEBUG", "true")
    monkeypatch.setenv("ACS_STORAGE__BASE_PATH", str(tmp_path / "artifacts"))
    monkeypatch.setenv("ACS_LOGGING__LEVEL", "DEBUG")

    # Create necessary directories
    (tmp_path / "artifacts").mkdir(exist_ok=True)
    (tmp_path / "logs").mkdir(exist_ok=True)


# Cleanup fixtures
@pytest.fixture(autouse=True)
async def cleanup_async_tasks():
    """Ensure all async tasks are cleaned up after each test."""
    yield

    # Cancel any remaining tasks
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()

    # Wait for cancellation
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
