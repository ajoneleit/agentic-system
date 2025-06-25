#!/usr/bin/env python3
"""Test Meta Agent with mocked Claude responses."""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4
from pprint import pprint

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.meta_agent import MetaAgent
from src.core.interfaces import TaskContext, Task, TaskPriority, AgentRole
from src.core.artifact_manager import ArtifactManager


async def test_with_mock():
    """Test Meta Agent decomposition with mocked Claude responses."""
    print("=== Meta Agent Test with Mocked Responses ===\n")
    
    # Get user input
    user_request = input("Enter your task (or press Enter for default): ").strip()
    if not user_request:
        user_request = "Create a simple hello world Python script"
    
    print(f"\n📋 Task: {user_request}")
    print("="*80)
    
    # Setup
    storage_path = Path("./projects")
    storage_path.mkdir(exist_ok=True)
    
    # Mock the Claude client
    with patch('src.agents.meta_agent.ClaudeClient') as mock_claude:
        # Create mock instance
        mock_client = MagicMock()
        mock_client.close = AsyncMock()  # Add async close method
        mock_claude.return_value = mock_client
        
        # Mock the decomposition response
        decomposition_response = {
            "tasks": [
                {
                    "name": "Create main script file",
                    "description": "Create a Python file with a simple hello world print statement",
                    "agent_type": "code_generation",
                    "complexity": "low",
                    "deliverable": "hello_world.py",
                    "dependencies": [],
                    "requirements": {
                        "content": "print('Hello, World!')",
                        "language": "python"
                    }
                },
                {
                    "name": "Add shebang and encoding",
                    "description": "Add proper shebang line and UTF-8 encoding declaration",
                    "agent_type": "code_generation",
                    "complexity": "low",
                    "deliverable": "hello_world.py (updated)",
                    "dependencies": ["Create main script file"],
                    "requirements": {
                        "shebang": "#!/usr/bin/env python3",
                        "encoding": "# -*- coding: utf-8 -*-"
                    }
                },
                {
                    "name": "Write unit test",
                    "description": "Create a simple test to verify the script runs and outputs correctly",
                    "agent_type": "test_generation",
                    "complexity": "low",
                    "deliverable": "test_hello_world.py",
                    "dependencies": ["Create main script file"],
                    "requirements": {
                        "test_framework": "unittest",
                        "test_output": "Hello, World!"
                    }
                },
                {
                    "name": "Create README",
                    "description": "Write a README.md explaining how to run the hello world script",
                    "agent_type": "documentation",
                    "complexity": "low",
                    "deliverable": "README.md",
                    "dependencies": ["Create main script file"],
                    "requirements": {
                        "sections": ["Description", "Usage", "Testing"]
                    }
                }
            ]
        }
        
        # Mock the dependency analysis response
        dependency_response = {
            "task_dependencies": {
                "Create main script file": [],
                "Add shebang and encoding": ["Create main script file"],
                "Write unit test": ["Create main script file"],
                "Create README": ["Create main script file"]
            }
        }
        
        # Setup mock responses
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(decomposition_response))]
        
        mock_dep_response = MagicMock()
        mock_dep_response.content = [MagicMock(text=json.dumps(dependency_response))]
        
        # Configure the mock to return different responses for different calls
        mock_client.create_message = AsyncMock(side_effect=[mock_response, mock_dep_response])
        
        # Create Meta Agent
        meta_agent = MetaAgent(artifact_storage_path=storage_path)
        
        # Create context
        context = TaskContext(
            project_root=storage_path,
            shared_memory={"project_name": "Hello World Test"},
            artifact_manager=ArtifactManager(storage_path=storage_path / "artifacts"),
            project_id=uuid4()
        )
        
        meta_agent.context = context
        
        try:
            print("\n🔍 Decomposing task...")
            print("(Using mocked Claude responses)\n")
            
            # Call decomposition
            subtasks = await meta_agent.decompose_task(user_request)
            
            print(f"✅ Decomposed into {len(subtasks)} subtasks:")
            print("="*80)
            
            # Display tasks
            for i, task in enumerate(subtasks, 1):
                print(f"\n📌 Subtask {i}: {task.name}")
                print(f"   Description: {task.description}")
                print(f"   Role: {task.required_role.value if task.required_role else 'Any'}")
                print(f"   Priority: {task.priority.value}")
                print(f"   Complexity: {task.estimated_complexity}")
                print(f"   Dependencies: {len(task.dependencies)}")
                
                # Show JSON
                task_dict = {
                    "id": str(task.id),
                    "name": task.name,
                    "description": task.description,
                    "required_role": task.required_role.value if task.required_role else None,
                    "priority": task.priority.value,
                    "dependencies": [str(d) for d in task.dependencies]
                }
                print(f"\n   JSON:")
                print("   " + json.dumps(task_dict, indent=2).replace("\n", "\n   "))
            
            # Show mock details
            print("\n\n📞 Mock Claude API Calls:")
            print("="*80)
            print(f"Total calls made: {mock_client.create_message.call_count}")
            
            for i, call in enumerate(mock_client.create_message.call_args_list, 1):
                print(f"\nCall {i}:")
                args, kwargs = call
                if 'messages' in kwargs:
                    msg = kwargs['messages'][0]['content']
                    print(f"  Prompt preview: {msg[:100]}...")
                if 'model' in kwargs:
                    print(f"  Model: {kwargs['model']}")
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            await meta_agent.shutdown()
    
    print("\n✅ Test complete!")


if __name__ == "__main__":
    print("This test uses mocked Claude responses - no API calls will be made.\n")
    asyncio.run(test_with_mock())