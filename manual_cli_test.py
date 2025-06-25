#!/usr/bin/env python3
"""Manual test script for Claude CLI integration."""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.sub_agent import CodeGeneratorAgent
from src.core.interfaces import Task, TaskContext


async def test_cli_manually():
    """Test the Claude CLI integration manually."""
    print("=== Manual Claude CLI Test ===\n")
    
    # Create a simple task
    task = Task(
        name="Generate Calculator",
        description="Create a simple calculator class",
        metadata={
            "specification": {
                "language": "python",
                "frameworks": [],
                "requirements": "Create a Calculator class with add, subtract, multiply, and divide methods"
            }
        }
    )
    
    # Create context
    context = TaskContext(
        project_root=Path("/tmp/test"),
        shared_memory={"project_name": "Calculator Project"}
    )
    
    # Create agent
    agent = CodeGeneratorAgent(uuid4())
    
    print("1. Initializing agent...")
    await agent.initialize(context)
    
    if agent.use_cli:
        print("✅ Agent is using Claude CLI")
        print(f"   CLI client: {agent.claude_cli_client}")
    else:
        print("❌ Agent is using API (CLI not available)")
        print("   Make sure 'claude' command is available in your PATH")
        return
    
    print("\n2. Executing task...")
    print("   This will call the Claude CLI with the code generation prompt")
    print("   You should see the CLI being invoked...\n")
    
    try:
        result = await agent.execute_task(task, context)
        
        if result.success:
            print("✅ Task completed successfully!")
            print(f"   Artifacts created: {len(result.artifacts)}")
            print(f"   Execution time: {result.execution_time:.2f}s")
            
            # If we had artifact manager, we could retrieve the content
            print("\n3. Task Result Details:")
            print(f"   Success: {result.success}")
            print(f"   Primary artifact: {result.primary_artifact}")
            print(f"   Errors: {result.errors}")
            print(f"   Warnings: {result.warnings}")
        else:
            print("❌ Task failed!")
            print(f"   Errors: {result.errors}")
            
    except Exception as e:
        print(f"❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()
    
    await agent.shutdown()
    print("\n✅ Test complete!")


async def test_cli_direct():
    """Test the CLI client directly."""
    print("=== Direct Claude CLI Client Test ===\n")
    
    from src.clients.claude_cli_client import ClaudeCLIClient
    
    client = ClaudeCLIClient()
    
    # Check availability
    print("1. Checking CLI availability...")
    available = await client.check_cli_available()
    print(f"   Available: {available}")
    
    if not available:
        print("   ❌ Claude CLI not found. Install it with: pip install claude-cli")
        return
    
    # Test direct code generation
    print("\n2. Testing direct code generation...")
    prompt = "Write a Python function that calculates the fibonacci sequence"
    
    try:
        response = await client.create_code(
            prompt=prompt,
            temperature=0.3,
            max_tokens=500
        )
        
        print("✅ Response received:")
        print("-" * 50)
        print(response)
        print("-" * 50)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test the message API compatibility
    print("\n3. Testing message API compatibility...")
    try:
        response = await client.create_message_for_code(
            messages=[{"role": "user", "content": "Write a function to check if a string is a palindrome"}],
            task_type="code",
            temperature=0.3
        )
        
        print("✅ API-style response:")
        print(f"   Model: {response.get('model')}")
        print(f"   Usage: {response.get('usage')}")
        print("\nGenerated code:")
        print("-" * 50)
        print(response['content'][0]['text'])
        print("-" * 50)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    await client.close()


async def main():
    """Run all tests."""
    print("Choose test mode:")
    print("1. Test full agent integration (uses CLI through agent)")
    print("2. Test CLI client directly")
    print("3. Run both tests")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        await test_cli_manually()
    elif choice == "2":
        await test_cli_direct()
    elif choice == "3":
        await test_cli_manually()
        print("\n" + "="*60 + "\n")
        await test_cli_direct()
    else:
        print("Invalid choice")


if __name__ == "__main__":
    asyncio.run(main())