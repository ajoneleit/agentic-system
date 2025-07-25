#!/usr/bin/env python3
"""Basic usage example for the Agentic Coding System."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_settings
from src.agents import MetaAgent
from src.core.interfaces import Task, TaskContext
from src.utils.app_logging import get_logger, setup_logging
from src.utils.health_check import validate_system_health

logger = get_logger(__name__)


async def demonstrate_basic_agent_system():
    """Demonstrate the full agent system with MetaAgent orchestration."""
    logger.info("=== Demonstrating Agent System ===")

    # First, run health check
    logger.info("Running system health check...")
    is_healthy, _ = await validate_system_health()

    if not is_healthy:
        logger.error("System is not healthy! Check the health report for details.")
        return

    logger.info("System is healthy, proceeding with demonstration...")

    # Get settings
    settings = get_settings()

    # Check if we have API key
    if not settings.api or not settings.api.key:
        logger.warning("""
No API key configured! The agent system requires a valid Anthropic API key.

To run this demo:
1. Get your API key from https://console.anthropic.com/
2. Set it in your .env file: ACS_API__KEY=your-key-here
3. Run this example again
""")
        return

    try:
        # Create MetaAgent
        logger.info("Initializing Meta Agent...")
        meta_agent = MetaAgent()

        # Initialize with context
        context = TaskContext(
            project_root=Path.cwd() / "projects" / "demo_project",
            shared_memory={
                "project_type": "demo",
                "language": "python",
            }
        )
        await meta_agent.initialize(context)

        # Example 1: Simple code generation
        logger.info("\n--- Example 1: Simple Code Generation ---")
        user_request = """
        Create a Python calculator class with the following methods:
        - add(a, b): returns sum of a and b
        - subtract(a, b): returns difference
        - multiply(a, b): returns product
        - divide(a, b): returns quotient (handle division by zero)
        Include proper docstrings and type hints.
        """

        logger.info("Processing user request...")
        result = await meta_agent.process_request(user_request)

        logger.info(f"""
Request completed!
- Tasks completed: {result.tasks_completed}
- Tasks failed: {result.tasks_failed}
- Success rate: {result.success_rate:.2%}
- Execution time: {result.execution_time:.2f} seconds
- Artifacts generated: {len(result.artifacts)}
""")

        # Example 2: More complex request (if first one succeeded)
        if result.success_rate > 0.5:
            logger.info("\n--- Example 2: Complex Project ---")
            complex_request = """
            Create a simple TODO API using FastAPI with:
            1. SQLite database using SQLAlchemy
            2. CRUD operations for todo items (create, read, update, delete)
            3. Todo model with: id, title, description, completed, created_at
            4. Input validation using Pydantic
            5. Basic unit tests for all endpoints
            6. API documentation
            """

            logger.info("Processing complex request...")
            result2 = await meta_agent.process_request(complex_request)

            logger.info(f"""
Complex request completed!
- Tasks completed: {result2.tasks_completed}
- Tasks failed: {result2.tasks_failed}
- Success rate: {result2.success_rate:.2%}
- Execution time: {result2.execution_time:.2f} seconds
""")

        # Show progress monitoring
        logger.info("\n--- System Progress Report ---")
        progress = await meta_agent.monitor_progress()

        if "aggregated_analysis" in progress and progress["aggregated_analysis"]:
            analysis = progress["aggregated_analysis"]
            logger.info(f"""
Overall Progress:
- Completion: {analysis.get('overall_progress', {}).get('completion_percentage', 0)}%
- Critical Path Status: {analysis.get('critical_path', {}).get('status', 'unknown')}
""")

        # Cleanup
        logger.info("\nShutting down Meta Agent...")
        await meta_agent.shutdown()

    except Exception as e:
        logger.error(f"Agent system demo failed: {e}", exc_info=True)


async def demonstrate_task_decomposition():
    """Demonstrate how MetaAgent decomposes tasks."""
    logger.info("\n=== Demonstrating Task Decomposition ===")

    settings = get_settings()
    if not settings.api or not settings.api.key:
        logger.warning("Skipping task decomposition demo - no API key")
        return

    try:
        meta_agent = MetaAgent()

        # Simple request
        request = "Create a Python script that fetches weather data from an API and displays it"

        logger.info(f"User request: {request}")
        logger.info("Decomposing into tasks...")

        tasks = await meta_agent.decompose_task(request)

        logger.info(f"\nDecomposed into {len(tasks)} tasks:")
        for i, task in enumerate(tasks, 1):
            deps = len(task.dependencies)
            logger.info(f"""
Task {i}: {task.name}
- Description: {task.description}
- Priority: {task.priority.value}
- Complexity: {task.estimated_complexity}
- Required Role: {task.required_role.value if task.required_role else 'any'}
- Dependencies: {deps} other task(s)
""")

        await meta_agent.shutdown()

    except Exception as e:
        logger.error(f"Task decomposition demo failed: {e}")


async def demonstrate_error_handling():
    """Demonstrate error handling capabilities."""
    from src.core.exceptions import (
        AgentError,
        TaskDecompositionError,
        TaskExecutionError,
    )

    logger.info("\n=== Demonstrating Error Handling ===")

    # Example 1: Task execution error
    try:
        raise TaskExecutionError(
            task_id=Task(name="Failed Task", description="Test").id,
            agent_id=Task(name="Test Agent", description="Test").id,
            reason="Simulated compilation failure"
        )
    except TaskExecutionError as e:
        logger.error(f"Caught task execution error: {e.message}")
        logger.debug(f"Error details: {e.to_dict()}")

    # Example 2: Task decomposition error
    try:
        raise TaskDecompositionError(
            task_id=Task(name="Bad Task", description="Test").id,
            user_prompt="Invalid prompt",
            reason="Could not parse user request"
        )
    except TaskDecompositionError as e:
        logger.error(f"Caught decomposition error: {e.message}")

    # Example 3: Agent error
    try:
        raise AgentError(
            agent_id=Task(name="Agent", description="Test").id,
            message="Agent initialization failed"
        )
    except AgentError as e:
        logger.error(f"Caught agent error: {e.message}")


async def main():
    """Main entry point."""
    print("=== Agentic Coding System - Usage Examples ===\n")

    # Setup logging
    setup_logging()

    # Run demonstrations
    await demonstrate_basic_agent_system()
    await demonstrate_task_decomposition()
    await demonstrate_error_handling()

    print("\n=== All demos completed! ===")


if __name__ == "__main__":
    asyncio.run(main())
