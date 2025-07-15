#!/usr/bin/env python3
"""Demo showing clean task decomposition output."""

import asyncio
import logging
import sys
from pathlib import Path

# Suppress all logging except critical errors
logging.basicConfig(level=logging.CRITICAL)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.meta_agent import MetaAgent
from src.core.interfaces import TaskContext

async def demo_task_decomposition():
    """Show clean task decomposition without verbose logging."""
    
    print("🌟 Agentic Coding System - Task Decomposition Demo")
    print("=" * 80)
    
    # Initialize system
    print("\n📦 Initializing MetaAgent...")
    projects_path = Path.cwd() / "projects"
    projects_path.mkdir(exist_ok=True)
    
    try:
        meta_agent = MetaAgent(artifact_storage_path=projects_path)
        context = TaskContext(project_root=projects_path)
        await meta_agent.initialize(context)
        print("✅ System initialized")
        
        # User request
        request = """Create a Python CLI tool that fetches the current weather for a given city
using an open weather API, caches results in a local SQLite DB, includes
unit tests, and provides documentation."""
        
        print(f"\n📝 User Request:")
        print("-" * 80)
        print(request)
        print("-" * 80)
        
        print("\n🔍 Decomposing into tasks (this may take a moment)...")
        
        # Get task decomposition
        tasks = await meta_agent.decompose_task(request)
        
        if tasks:
            # Create task ID mapping
            task_id_map = {str(task.id): f"T{i}" for i, task in enumerate(tasks, 1)}
            
            print("\n📋 Task Decomposition:")
            print("=" * 80)
            
            for i, task in enumerate(tasks, 1):
                # Format dependencies
                if task.dependencies:
                    deps = [task_id_map.get(str(d), str(d)[:8]) for d in task.dependencies]
                    deps_str = f"[{', '.join(deps)}]"
                else:
                    deps_str = "None"
                
                print(f"\n⏳ Task T{i}: {task.name}")
                print(f"   Agent: {task.required_role.value if task.required_role else 'any'}")
                print(f"   Dependencies: {deps_str}")
                print(f"   Complexity: {task.estimated_complexity}")
            
            print("\n" + "=" * 80)
            
            # Dependency analysis
            print("\n🔗 Dependency Analysis:")
            print("-" * 80)
            
            # Find independent tasks
            independent = [t for t in tasks if not t.dependencies]
            if independent:
                print("\n✨ Can start immediately:")
                for task in independent:
                    tid = task_id_map[str(task.id)]
                    print(f"   • {tid}: {task.name}")
            
            # Find bottlenecks
            dep_counts = {}
            for task in tasks:
                for dep in task.dependencies:
                    dep_str = str(dep)
                    dep_counts[dep_str] = dep_counts.get(dep_str, 0) + 1
            
            if dep_counts:
                bottlenecks = sorted(dep_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                print("\n⚠️  Key dependencies (blocking the most tasks):")
                for task_id, count in bottlenecks:
                    tid = task_id_map.get(task_id, task_id[:8])
                    task_name = next((t.name for t in tasks if str(t.id) == task_id), "Unknown")
                    print(f"   • {tid}: {task_name} (blocks {count} other tasks)")
            
            print("-" * 80)
            
            # Project info
            project_name = await meta_agent._generate_project_name(request)
            print(f"\n📁 Project name: {project_name}")
            print(f"📂 Files will be created in: projects/{project_name}/workspace/")
            
        else:
            print("\n❌ Failed to decompose tasks")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ Demo complete!")

if __name__ == "__main__":
    asyncio.run(demo_task_decomposition())