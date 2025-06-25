#!/usr/bin/env python3
"""Verify that agents are actually using CLI instead of API."""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch, MagicMock, AsyncMock

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.sub_agent import CodeGeneratorAgent
from src.core.interfaces import Task, TaskContext


async def verify_cli_usage():
    """Verify that the agent uses CLI when available."""
    print("=== Verifying CLI Usage in Agents ===\n")
    
    # Create task and context
    task = Task(
        name="Test Task",
        description="Test task for CLI verification",
        metadata={"specification": {"language": "python"}}
    )
    
    context = TaskContext(
        project_root=Path("/tmp/test"),
        shared_memory={}
    )
    
    # Test 1: When CLI is available
    print("Test 1: CLI Available")
    print("-" * 30)
    
    agent1 = CodeGeneratorAgent(uuid4())
    
    # Track what gets called
    api_called = False
    cli_called = False
    
    # Patch the clients to track calls
    with patch('src.agents.sub_agent.ClaudeClient') as mock_api, \
         patch('src.agents.sub_agent.ClaudeCLIClient') as mock_cli:
        
        # Setup CLI mock
        mock_cli_instance = mock_cli.return_value
        mock_cli_instance.check_cli_available = AsyncMock(return_value=True)
        mock_cli_instance.close = AsyncMock()
        
        async def mock_cli_create_message(*args, **kwargs):
            nonlocal cli_called
            cli_called = True
            return {
                "content": [{
                    "text": '{"code": "def test(): pass", "filename": "test.py"}',
                    "type": "text"
                }]
            }
        
        mock_cli_instance.create_message_for_code = mock_cli_create_message
        
        # Setup API mock
        mock_api_instance = mock_api.return_value
        
        async def mock_api_create_message(*args, **kwargs):
            nonlocal api_called
            api_called = True
            return MagicMock(content=[MagicMock(text='{"code": "def test(): pass"}')])
        
        mock_api_instance.create_message = mock_api_create_message
        
        # Initialize and execute
        await agent1.initialize(context)
        
        print(f"Agent initialized:")
        print(f"  - use_cli: {agent1.use_cli}")
        print(f"  - claude_client: {agent1.claude_client}")
        print(f"  - claude_cli_client: {agent1.claude_cli_client}")
        
        result = await agent1.execute_task(task, context)
        
        print(f"\nExecution complete:")
        print(f"  - CLI called: {cli_called}")
        print(f"  - API called: {api_called}")
        print(f"  - Success: {result.success}")
        
        assert cli_called and not api_called, "CLI should be used when available!"
        print("✅ CLI was used (API not called)")
        
        await agent1.shutdown()
    
    # Test 2: When CLI is not available
    print("\n\nTest 2: CLI Not Available")
    print("-" * 30)
    
    agent2 = CodeGeneratorAgent(uuid4())
    
    api_called = False
    cli_called = False
    
    with patch('src.agents.sub_agent.ClaudeClient') as mock_api, \
         patch('src.agents.sub_agent.ClaudeCLIClient') as mock_cli:
        
        # Setup CLI mock (not available)
        mock_cli_instance = mock_cli.return_value
        mock_cli_instance.check_cli_available = AsyncMock(return_value=False)
        mock_cli_instance.close = AsyncMock()
        
        # Setup API mock
        mock_api_instance = mock_api.return_value
        mock_api_instance.close = AsyncMock()
        
        async def mock_api_create_message(*args, **kwargs):
            nonlocal api_called
            api_called = True
            return MagicMock(content=[MagicMock(text='{"code": "def test(): pass", "filename": "test.py"}')])
        
        mock_api_instance.create_message = mock_api_create_message
        
        # Initialize and execute
        await agent2.initialize(context)
        
        print(f"Agent initialized:")
        print(f"  - use_cli: {agent2.use_cli}")
        print(f"  - claude_client: {agent2.claude_client}")
        print(f"  - claude_cli_client: {agent2.claude_cli_client}")
        
        result = await agent2.execute_task(task, context)
        
        print(f"\nExecution complete:")
        print(f"  - CLI called: {cli_called}")
        print(f"  - API called: {api_called}")
        print(f"  - Success: {result.success}")
        
        assert api_called and not cli_called, "API should be used when CLI not available!"
        print("✅ API was used as fallback (CLI not called)")
        
        await agent2.shutdown()
    
    print("\n✅ All verification tests passed!")
    print("\nConclusion: Agents correctly use CLI when available and fall back to API when not.")


if __name__ == "__main__":
    asyncio.run(verify_cli_usage())