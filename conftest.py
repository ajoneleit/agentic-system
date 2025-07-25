"""Pytest configuration for the Agentic Coding System."""

import asyncio
import logging
import os
import sys
from pathlib import Path

import pytest
import structlog

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

# Disable structlog during tests to avoid logging errors
os.environ["STRUCTLOG_TESTING"] = "true"


@pytest.fixture(scope="session", autouse=True)
def setup_test_logging():
    """Configure logging for tests."""
    # Disable all logging during tests
    logging.disable(logging.CRITICAL)

    # Configure structlog for testing
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False
    )

    yield

    # Re-enable logging after tests
    logging.disable(logging.NOTSET)


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use WindowsSelectorEventLoopPolicy on Windows."""
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.get_event_loop_policy()


@pytest.fixture
def anyio_backend():
    """Use asyncio backend for anyio."""
    return "asyncio"


@pytest.fixture(autouse=True)
async def cleanup_tasks():
    """Clean up any pending tasks after each test."""
    yield

    # Get all tasks
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    # Cancel them
    for task in tasks:
        task.cancel()

    # Wait for them to be cancelled
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.fixture
def mock_claude_client():
    """Mock ClaudeClient for tests."""
    from unittest.mock import AsyncMock, MagicMock

    client = MagicMock()
    client.create_message = AsyncMock()
    client.close = AsyncMock()
    return client
