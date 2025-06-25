#!/usr/bin/env python3
"""Simple non-interactive test for Meta Agent task decomposition."""

import asyncio
import json
import sys
from pathlib import Path
from pprint import pprint
from uuid import uuid4

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.meta_agent import MetaAgent
from src.core.interfaces import TaskContext
from src.core.artifact_manager import ArtifactManager


async def test_decomposition():
    """Test Meta Agent task decomposition with a simple task."""
    
    # Task to decompose
    user_request = "Create a simple calculator with add and subtract functions"
    
    print(f"📋 Task: {user_request}")
    print("="*80)
    
    # Create Meta Agent
    print("\n🤖 Initializing Meta Agent...")
    storage_path = Path("./projects")
    storage_path.mkdir(exist_ok=True)
    
    # Create artifact manager
    artifact_manager = ArtifactManager(storage_path=storage_path / "artifacts")
    
    # Initialize Meta Agent
    meta_agent = MetaAgent(artifact_storage_path=storage_path)
    
    # Create context
    context = TaskContext(
        project_root=storage_path,
        shared_memory={
            "project_name": "Calculator Test",
            "requirements": user_request
        },
        artifact_manager=artifact_manager,
        project_id=uuid4()
    )
    
    # Initialize meta agent context
    meta_agent.context = context
    
    try:
        print("\n🔍 Decomposing task into subtasks...")
        print("(This calls Claude Opus to analyze and break down the task)\n")
        
        # Call the decompose_task method
        subtasks = await meta_agent.decompose_task(user_request)
        
        print(f"\n✅ Decomposed into {len(subtasks)} subtasks:")
        print("="*80)
        
        # Display each subtask with full details
        for i, task in enumerate(subtasks, 1):
            print(f"\n📌 Subtask {i}: {task.name}")
            print("-"*40)
            
            # Convert task to dict for display
            task_dict = {
                "id": str(task.id),
                "name": task.name,
                "description": task.description,
                "required_role": task.required_role.value if task.required_role else None,
                "priority": task.priority.value,
                "estimated_complexity": task.estimated_complexity,
                "dependencies": [str(dep) for dep in task.dependencies],
                "metadata": task.metadata,
                "tags": list(task.tags) if task.tags else []
            }
            
            print("\nJSON representation:")
            print(json.dumps(task_dict, indent=2))
            
        print("\n✅ Test complete!")
        
    except Exception as e:
        print(f"\n❌ Error during decomposition: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        await meta_agent.shutdown()


if __name__ == "__main__":
    print("Starting Meta Agent Task Decomposition Test...")
    print("Note: This will use Claude Opus for task decomposition")
    print("Make sure your ANTHROPIC_API_KEY is set in .env\n")
    
    # Run in virtual environment
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "asyncio", "run", "-c", 
         "import sys; sys.path.insert(0, '.'); "
         "from test_meta_agent_simple import test_decomposition; "
         "import asyncio; asyncio.run(test_decomposition())"],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        # Try running directly
        asyncio.run(test_decomposition())