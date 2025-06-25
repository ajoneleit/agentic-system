#!/usr/bin/env python3
"""Non-interactive test for full Meta Agent execution."""

import asyncio
import sys
from pathlib import Path
from pprint import pprint

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.meta_agent import MetaAgent


async def test_full_execution():
    """Test full Meta Agent execution with a simple task."""
    
    # Task to execute
    user_request = "Create a simple hello world python script"
    
    print(f"📋 Task: {user_request}")
    print("="*80)
    
    # Create Meta Agent
    print("\n🤖 Initializing Meta Agent...")
    storage_path = Path("./projects")
    storage_path.mkdir(exist_ok=True)
    
    meta_agent = MetaAgent(artifact_storage_path=storage_path)
    
    try:
        print("\n🚀 Processing request...")
        print("(This will decompose, spawn agents, and execute tasks)\n")
        
        # Process the request
        result = await meta_agent.process_request(user_request)
        
        print("\n✅ Execution complete!")
        print("="*80)
        
        print(f"\nResults:")
        print(f"  • Artifacts created: {len(result.artifacts)}")
        print(f"  • Tasks completed: {result.tasks_completed}")
        print(f"  • Tasks failed: {result.tasks_failed}")
        print(f"  • Success rate: {result.success_rate:.1%}")
        print(f"  • Execution time: {result.execution_time:.2f}s")
        
        if result.artifacts:
            print("\n📦 Artifacts created:")
            for artifact in result.artifacts:
                print(f"  • {artifact.name} ({artifact.type.value})")
                print(f"    Path: {artifact.path}")
                print(f"    Size: {len(artifact.content)} chars")
                if len(artifact.content) < 200:
                    print(f"    Content:\n{artifact.content}")
                else:
                    print(f"    Content preview:\n{artifact.content[:200]}...")
        
        if result.metadata.get("errors"):
            print("\n⚠️ Errors encountered:")
            for error in result.metadata["errors"]:
                print(f"  • {error}")
        
        if result.metadata.get("warnings"):
            print("\n⚠️ Warnings:")
            for warning in result.metadata["warnings"]:
                print(f"  • {warning}")
        
        print("\n📊 Task Results:")
        for task_id, task_result in result.metadata.get("task_results", {}).items():
            print(f"\n  Task {task_id}:")
            print(f"    • Success: {task_result['success']}")
            print(f"    • Artifacts: {task_result['artifacts']}")
            print(f"    • Execution time: {task_result['execution_time']:.2f}s")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await meta_agent.shutdown()
        print("\n✅ Test complete!")


if __name__ == "__main__":
    print("Starting Full Meta Agent Execution Test...")
    print("Note: This will use Claude for task decomposition and execution")
    print("Make sure your ANTHROPIC_API_KEY is set in .env\n")
    
    asyncio.run(test_full_execution())