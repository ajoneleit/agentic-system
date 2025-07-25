#!/usr/bin/env python3
"""Demo showing clean task decomposition output with minimal logging."""

import asyncio
import logging
import sys
from pathlib import Path

# Configure minimal logging
logging.basicConfig(
    level=logging.CRITICAL,
    format='%(message)s'
)

# Suppress all loggers except what we explicitly want
for logger_name in ['src', 'urllib3', 'asyncio', 'structlog']:
    logging.getLogger(logger_name).setLevel(logging.CRITICAL)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.meta_agent import MetaAgent
from src.core.interfaces import TaskContext


async def demo_task_decomposition():
    """Show clean task decomposition without verbose logging."""
    print("🌟 Agentic Coding System - Task Decomposition Demo")
    print("=" * 80)

    # Initialize system quietly
    print("\n📦 Initializing system...")
    projects_path = Path.cwd() / "projects"
    projects_path.mkdir(exist_ok=True)

    try:
        meta_agent = MetaAgent(artifact_storage_path=projects_path)
        context = TaskContext(project_root=projects_path)
        await meta_agent.initialize(context)
        print("✅ System ready")

        # User request
        request = """Create a Python CLI tool that fetches the current weather for a given city
using an open weather API, caches results in a local SQLite DB, includes
unit tests, and provides documentation."""

        print("\n📝 User Request:")
        print("-" * 80)
        print(request)
        print("-" * 80)

        print("\n🔍 Analyzing request and creating task breakdown...")
        print("   (This uses AI to understand the requirements)")

        # Get task decomposition
        tasks = await meta_agent.decompose_task(request)

        if tasks:
            # Create task ID mapping for readability
            task_id_map = {str(task.id): f"T{i}" for i, task in enumerate(tasks, 1)}

            print(f"\n✅ Identified {len(tasks)} tasks needed")
            print("\n📋 Task Breakdown:")
            print("=" * 80)

            # Group tasks by role
            core_tasks = [t for t in tasks if t.required_role and t.required_role.value == "core_logic"]
            test_tasks = [t for t in tasks if t.required_role and t.required_role.value == "testing"]
            doc_tasks = [t for t in tasks if t.required_role and t.required_role.value == "documentation"]
            other_tasks = [t for t in tasks if t not in core_tasks + test_tasks + doc_tasks]

            # Print by category
            if core_tasks:
                print("\n🔧 Core Development Tasks:")
                for task in core_tasks:
                    tid = task_id_map[str(task.id)]
                    deps = [task_id_map.get(str(d), str(d)[:8]) for d in task.dependencies]
                    deps_str = f" (depends on: {', '.join(deps)})" if deps else ""
                    print(f"   {tid}: {task.name}{deps_str}")

            if test_tasks:
                print("\n🧪 Testing Tasks:")
                for task in test_tasks:
                    tid = task_id_map[str(task.id)]
                    deps = [task_id_map.get(str(d), str(d)[:8]) for d in task.dependencies]
                    deps_str = f" (depends on: {', '.join(deps)})" if deps else ""
                    print(f"   {tid}: {task.name}{deps_str}")

            if doc_tasks:
                print("\n📚 Documentation Tasks:")
                for task in doc_tasks:
                    tid = task_id_map[str(task.id)]
                    deps = [task_id_map.get(str(d), str(d)[:8]) for d in task.dependencies]
                    deps_str = f" (depends on: {', '.join(deps)})" if deps else ""
                    print(f"   {tid}: {task.name}{deps_str}")

            if other_tasks:
                print("\n📦 Other Tasks:")
                for task in other_tasks:
                    tid = task_id_map[str(task.id)]
                    deps = [task_id_map.get(str(d), str(d)[:8]) for d in task.dependencies]
                    deps_str = f" (depends on: {', '.join(deps)})" if deps else ""
                    print(f"   {tid}: {task.name}{deps_str}")

            print("\n" + "=" * 80)

            # Execution order analysis
            print("\n🔗 Execution Order Analysis:")
            print("-" * 80)

            # Find tasks by dependency level
            levels = {}

            # Start with tasks that have no dependencies
            level_0 = [t for t in tasks if not t.dependencies]
            if level_0:
                levels[0] = level_0

            # Find subsequent levels
            level = 1
            remaining = [t for t in tasks if t.dependencies]
            while remaining and level < 10:  # Prevent infinite loop
                current_level = []
                for task in remaining[:]:
                    # Check if all dependencies are in previous levels
                    deps_satisfied = True
                    for dep_id in task.dependencies:
                        found = False
                        for prev_level in range(level):
                            if any(t.id == dep_id for t in levels.get(prev_level, [])):
                                found = True
                                break
                        if not found:
                            deps_satisfied = False
                            break

                    if deps_satisfied:
                        current_level.append(task)
                        remaining.remove(task)

                if current_level:
                    levels[level] = current_level
                    level += 1
                else:
                    break

            # Print execution waves
            for wave, wave_tasks in sorted(levels.items()):
                print(f"\n🌊 Wave {wave + 1} (can run in parallel):")
                for task in wave_tasks:
                    tid = task_id_map[str(task.id)]
                    print(f"   • {tid}: {task.name}")

            print("-" * 80)

            # Project info
            project_name = await meta_agent._generate_project_name(request)
            print("\n📁 Project Configuration:")
            print(f"   Name: {project_name}")
            print(f"   Location: projects/{project_name}/workspace/")
            print(f"   Total Tasks: {len(tasks)}")
            print(f"   Estimated Complexity: {max(t.estimated_complexity for t in tasks)}")

        else:
            print("\n❌ Failed to decompose tasks")

    except Exception as e:
        print(f"\n❌ Error: {e}")

    print("\n✅ Demo complete!")

if __name__ == "__main__":
    asyncio.run(demo_task_decomposition())
