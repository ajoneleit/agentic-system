#!/usr/bin/env python3
"""Non-interactive test for full Meta Agent execution with enhanced output."""

import asyncio
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.meta_agent import MetaAgent
from src.core.interfaces import Task


def print_task_decomposition(tasks: List[Task]):
    """Print detailed task decomposition information."""
    print("\n📋 Task Decomposition:")
    print("=" * 80)
    
    # Create mappings for both IDs and names
    task_id_map = {str(task.id): f"T{i}" for i, task in enumerate(tasks, 1)}
    task_name_map = {str(task.id): task.name for task in tasks}
    
    for i, task in enumerate(tasks, 1):
        # Format dependencies with actual task names
        deps = []
        if task.dependencies:
            deps = [task_name_map.get(str(d), f"Unknown Task {str(d)[:8]}") for d in task.dependencies]
            deps_str = f"[{', '.join(deps)}]"
        else:
            deps_str = "None"
        
        # Get role
        role = task.required_role.value if task.required_role else "any"
        
        print(f"\n🔸 Task {i} (T{i}): {task.name}")
        print(f"   Description: {task.description}")
        print(f"   Role: {role}")
        print(f"   Priority: {task.priority.value}")
        print(f"   Complexity: {task.estimated_complexity}")
        print(f"   Dependencies: {deps_str}")
        
        # Show metadata if available
        if task.metadata:
            if "deliverable" in task.metadata:
                print(f"   Deliverable: {task.metadata['deliverable']}")
    
    print("\n" + "=" * 80)


def print_dependency_graph(tasks: List[Task]):
    """Print ASCII dependency graph."""
    print("\n🔗 Dependency Graph:")
    print("-" * 80)
    
    # Create ID and name mappings
    task_id_map = {str(task.id): f"T{i}" for i, task in enumerate(tasks, 1)}
    task_name_map = {str(task.id): task.name for task in tasks}
    
    # Find root tasks (no dependencies)
    root_tasks = [t for t in tasks if not t.dependencies]
    if root_tasks:
        print("\n✨ Entry Points (can start immediately):")
        for task in root_tasks:
            tid = task_id_map[str(task.id)]
            print(f"   {tid}: {task.name}")
    
    # Show dependency flow with task names (arrows point right)
    print("\n📊 Dependency Flow:")
    for task in tasks:
        if task.dependencies:
            # Show as: "Dependency1 Name, Dependency2 Name → Task Name"
            dep_names = [task_name_map.get(str(d), f"Unknown {str(d)[:8]}") for d in task.dependencies]
            print(f"   {', '.join(dep_names)} → {task.name}")
    
    # Identify critical path (tasks that block the most others)
    dependency_counts = {}
    for task in tasks:
        for dep in task.dependencies:
            dep_str = str(dep)
            dependency_counts[dep_str] = dependency_counts.get(dep_str, 0) + 1
    
    if dependency_counts:
        bottlenecks = sorted(dependency_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        print("\n⚠️  Critical Tasks (blocking the most others):")
        for task_id, count in bottlenecks:
            task_name = next((t.name for t in tasks if str(t.id) == task_id), "Unknown")
            print(f"   {task_name} (blocks {count} tasks)")
    
    print("-" * 80)


def print_task_execution_start(task_name: str, role: str = None):
    """Print when a task starts executing."""
    print(f"\n🚀 Starting Task: {task_name}")
    if role:
        print(f"   Agent Role: {role}")
    print(f"   Time: {datetime.now().strftime('%H:%M:%S')}")


def print_task_execution_complete(task_name: str, success: bool, duration: float = None, error: str = None):
    """Print when a task completes."""
    status_icon = "✅" if success else "❌"
    print(f"\n{status_icon} Completed Task: {task_name}")
    print(f"   Status: {'SUCCESS' if success else 'FAILED'}")
    if duration:
        print(f"   Duration: {duration:.2f}s")
    if error:
        print(f"   Error: {error}")


async def test_full_execution():
    """Test full Meta Agent execution with enhanced output."""
    
    # Configure logging to reduce noise
    logging.getLogger("src.agents").setLevel(logging.WARNING)
    logging.getLogger("src.clients").setLevel(logging.WARNING)
    logging.getLogger("src.core").setLevel(logging.WARNING)
    logging.getLogger("src.utils").setLevel(logging.WARNING)
    
    # Task to execute
    user_request = input("Please enter the task prompt: ")
    
    print(f"📋 User Request: {user_request}")
    print("="*80)
    
    # Create Meta Agent
    print("\n🤖 Initializing Meta Agent...")
    storage_path = Path("./projects")
    storage_path.mkdir(exist_ok=True)
    
    meta_agent = MetaAgent(artifact_storage_path=storage_path)
    
    # Store original methods for interception
    original_decompose = meta_agent.decompose_task
    original_coordinate = meta_agent.coordinate_execution
    original_execute_task = meta_agent._execute_task_with_retry
    
    # Variables to store decomposed tasks
    decomposed_tasks = []
    task_map = {}  # Map task ID to name for execution tracking
    
    # Intercept decompose_task to print tasks immediately
    async def intercepted_decompose(user_request):
        tasks = await original_decompose(user_request)
        decomposed_tasks.extend(tasks)
        
        # Create task map
        for i, task in enumerate(tasks, 1):
            task_map[str(task.id)] = f"T{i}: {task.name}"
        
        # Print task decomposition immediately
        print("\n🔍 Task decomposition complete!")
        print_task_decomposition(tasks)
        print_dependency_graph(tasks)
        
        return tasks
    
    # Intercept coordinate_execution to track progress
    async def intercepted_coordinate(tasks, context):
        print("\n🚀 Starting task execution...")
        print("="*80)
        return await original_coordinate(tasks, context)
    
    # Intercept task execution to print when each task starts and completes
    async def intercepted_execute_task(task, agent, context):
        print(f"\n▶️  Executing task: {task.name}")
        start_time = datetime.now()
        
        try:
            result = await original_execute_task(task, agent, context)
            duration = (datetime.now() - start_time).total_seconds()
            
            if result.success:
                print(f"✅ Completed: {task.name} (took {duration:.2f}s)")
            else:
                error_msg = result.errors[0] if result.errors else "Unknown error"
                print(f"❌ Failed: {task.name} - {error_msg} (took {duration:.2f}s)")
            
            return result
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            print(f"❌ Failed: {task.name} - {str(e)} (took {duration:.2f}s)")
            raise
    
    # Apply interceptions
    meta_agent.decompose_task = intercepted_decompose
    meta_agent.coordinate_execution = intercepted_coordinate
    meta_agent._execute_task_with_retry = intercepted_execute_task
    
    try:
        # Track start time
        start_time = datetime.now()
        
        # Process the request
        print("\n📝 Processing request...")
        result = await meta_agent.process_request(user_request)
        
        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()
        
        print("\n\n✅ Execution Complete!")
        print("="*80)
        
        print(f"\n📊 Execution Summary:")
        print(f"  • Success: {result.success}")
        print(f"  • Tasks completed: {result.tasks_completed}")
        print(f"  • Tasks failed: {result.tasks_failed}")
        print(f"  • Success rate: {result.success_rate:.1%}")
        print(f"  • Total execution time: {duration:.2f}s")
        
        if result.artifacts:
            print(f"\n📦 Artifacts Created ({len(result.artifacts)} total):")
            for artifact in result.artifacts:
                print(f"\n  • {artifact.name} ({artifact.type.value})")
                print(f"    Path: {artifact.path}")
                print(f"    Size: {len(artifact.content)} chars")
        
        # Show task results if available
        if result.metadata.get("task_results"):
            print("\n📊 Individual Task Results:")
            task_results = result.metadata["task_results"]
            
            for task_id, task_result in task_results.items():
                task_label = task_map.get(task_id, f"Task {task_id[:8]}")
                status_icon = "✅" if task_result.get('success', False) else "❌"
                print(f"\n  {status_icon} {task_label}")
                print(f"     Success: {task_result.get('success', False)}")
                if 'execution_time' in task_result:
                    print(f"     Execution time: {task_result['execution_time']:.2f}s")
                if 'retry_count' in task_result:
                    print(f"     Retries: {task_result['retry_count']}")
        
        # Show any errors
        if result.metadata.get("errors"):
            print("\n⚠️ Errors Encountered:")
            for error in result.metadata["errors"][:5]:  # Limit to first 5
                print(f"  • {error}")
        
        # Retry information
        if result.metadata.get("retry_summary"):
            print("\n🔄 Retry Summary:")
            for task_id, count in result.metadata["retry_summary"].items():
                task_label = task_map.get(task_id, f"Task {task_id[:8]}")
                print(f"  • {task_label}: {count} retries")
        
    except Exception as e:
        print(f"\n❌ Fatal Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await meta_agent.shutdown()
        print("\n✅ Test complete!")


if __name__ == "__main__":
    print("🌟 Enhanced Meta Agent Execution Test")
    print("This will show detailed task decomposition and execution progress")
    print("")
    
    asyncio.run(test_full_execution())