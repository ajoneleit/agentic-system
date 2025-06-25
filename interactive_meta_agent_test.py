#!/usr/bin/env python3
"""Interactive test for Meta Agent task decomposition."""

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


async def test_task_decomposition():
    """Test Meta Agent task decomposition interactively."""
    print("=== Meta Agent Task Decomposition Test ===\n")
    
    # Get user input
    print("Enter a task description (or press Enter for default):")
    print("Default: 'Create a Python web scraper that extracts product prices from an e-commerce website'")
    user_request = input("\nYour task: ").strip()
    
    if not user_request:
        user_request = "Create a Python web scraper that extracts product prices from an e-commerce website"
    
    print(f"\n📋 Task: {user_request}")
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
            "project_name": "Interactive Test",
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
        
        # Call the decompose_task method directly
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
            
        # Show dependency analysis
        print("\n\n🔗 Dependency Analysis:")
        print("="*80)
        
        # Analyze dependencies
        print("\nCalling Claude to analyze task dependencies...")
        dependencies = await meta_agent._analyze_dependencies(subtasks)
        
        print("\nDependency structure:")
        if dependencies:
            for task_id, deps in dependencies.items():
                task = next((t for t in subtasks if str(t.id) == task_id), None)
                if task and deps:
                    print(f"\n'{task.name}' depends on:")
                    for dep_id in deps:
                        dep_task = next((t for t in subtasks if str(t.id) == dep_id), None)
                        if dep_task:
                            print(f"  → {dep_task.name}")
        else:
            print("No dependency analysis available")
        
        # Show execution order
        print("\n\n📊 Execution Plan:")
        print("="*80)
        
        # Determine execution order
        execution_order = []
        completed = set()
        
        # Use dependencies if available, otherwise use task dependencies directly
        if dependencies:
            while len(completed) < len(subtasks):
                for task in subtasks:
                    task_id = str(task.id)
                    if task_id in completed:
                        continue
                        
                    # Check if all dependencies are completed
                    task_deps = dependencies.get(task_id, [])
                    if all(dep in completed for dep in task_deps):
                        execution_order.append(task)
                        completed.add(task_id)
        else:
            # Fallback: use task's own dependencies
            while len(completed) < len(subtasks):
                for task in subtasks:
                    if task.id in completed:
                        continue
                        
                    # Check if all dependencies are completed
                    if all(dep in completed for dep in task.dependencies):
                        execution_order.append(task)
                        completed.add(task.id)
        
        print("\nTasks will be executed in this order:")
        for i, task in enumerate(execution_order, 1):
            if dependencies:
                deps = dependencies.get(str(task.id), [])
            else:
                deps = [str(d) for d in task.dependencies]
            deps_str = f" (depends on: {len(deps)} tasks)" if deps else " (no dependencies)"
            print(f"{i}. {task.name} - Role: {task.required_role.value if task.required_role else 'Any'}{deps_str}")
        
        # Show what agents would be spawned
        print("\n\n👥 Agents to be spawned:")
        print("="*80)
        
        roles_needed = set()
        for task in subtasks:
            if task.required_role:
                roles_needed.add(task.required_role.value)
        
        print(f"\nUnique agent roles needed: {len(roles_needed)}")
        for role in sorted(roles_needed):
            task_count = sum(1 for t in subtasks if t.required_role and t.required_role.value == role)
            print(f"  • {role}: {task_count} tasks")
        
        # Option to see the raw Claude response
        print("\n\n💭 Would you like to see the raw task decomposition prompt? (y/n)")
        if input().lower() == 'y':
            from src.prompts.task_decomposition import get_decomposition_prompt
            prompt_template = get_decomposition_prompt()
            prompt = prompt_template.render(user_request=user_request)
            print("\nPrompt sent to Claude:")
            print("-"*80)
            print(prompt)
            print("-"*80)
        
    except Exception as e:
        print(f"\n❌ Error during decomposition: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        await meta_agent.shutdown()
        print("\n\n✅ Test complete!")


async def test_full_execution():
    """Test full Meta Agent execution with subtask details."""
    print("\n=== Full Meta Agent Execution Test ===\n")
    
    print("Enter a task (or press Enter for default):")
    print("Default: 'Create a simple calculator with add and subtract functions'")
    user_request = input("\nYour task: ").strip()
    
    if not user_request:
        user_request = "Create a simple calculator with add and subtract functions"
    
    print(f"\n📋 Task: {user_request}")
    print("="*80)
    
    # Create Meta Agent
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
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await meta_agent.shutdown()


async def main():
    """Main interactive menu."""
    while True:
        print("\n" + "="*60)
        print("Meta Agent Interactive Test")
        print("="*60)
        print("\nChoose an option:")
        print("1. Test task decomposition only (see all subtask JSONs)")
        print("2. Test full execution (decompose + execute)")
        print("3. Exit")
        
        choice = input("\nEnter choice (1-3): ").strip()
        
        if choice == "1":
            await test_task_decomposition()
        elif choice == "2":
            await test_full_execution()
        elif choice == "3":
            print("\nGoodbye!")
            break
        else:
            print("Invalid choice, please try again.")
        
        if choice in ["1", "2"]:
            input("\nPress Enter to continue...")


if __name__ == "__main__":
    print("Starting Meta Agent Interactive Test...")
    print("Note: This will use Claude Opus for task decomposition")
    print("Make sure your ANTHROPIC_API_KEY is set in .env\n")
    
    asyncio.run(main())