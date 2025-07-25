#!/usr/bin/env python3
"""Self-contained demo of the Agentic Coding System.
Tests the full workflow from task decomposition to verification.
"""

import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Import real classes
try:
    from src.agents.meta_agent import MetaAgent
    from src.core.interfaces import TaskStatus
    from src.utils.app_logging import LogLevel, setup_logging
except ImportError as e:
    print(f"🚨 Import Error: {e}")
    print("Please ensure all modules are properly installed")
    sys.exit(1)

# Demo configuration
USER_REQUEST = """
Create a Python CLI tool that fetches the current weather for a given city
using an open weather API, caches results in a local SQLite DB, includes
unit tests, and provides documentation.
"""
MAX_TOTAL_SECONDS = 600  # 10 minutes timeout
LOG_LEVEL = "info"
SHOW_GRAPH_PNG_PATH = "task_graph.png"

# Create temp directory
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
DEMO_DIR = Path(f".demo_run_{timestamp}")


def print_header():
    """Print demo header."""
    print(f"### 🌤 Agentic Coding System DEMO (log-level {LOG_LEVEL})")
    print("=" * 70)


def print_task_summary(tasks):
    """Print task decomposition summary."""
    print("\n📋 Task Decomposition Summary:")
    print("=" * 80)

    # Create mappings for IDs and names
    task_id_map = {str(task.id): f"T{i}" for i, task in enumerate(tasks, 1)}
    task_name_map = {str(task.id): task.name for task in tasks}

    for i, task in enumerate(tasks, 1):
        # Format dependencies using actual task names
        if task.dependencies:
            deps = [task_name_map.get(str(d), f"Unknown {str(d)[:8]}") for d in task.dependencies]
            deps_str = f"[{', '.join(deps)}]"
        else:
            deps_str = "None"

        # Status indicator
        status_icon = "⏳" if task.status.value == "pending" else "✅"

        print(f"\n{status_icon} Task {i} (T{i}): {task.name}")
        print(f"   Role: {task.required_role.value if task.required_role else 'any'}")
        print(f"   Dependencies: {deps_str}")
        print(f"   Complexity: {task.estimated_complexity}")

    print("\n" + "=" * 80)

    # Print dependency analysis
    print_dependency_analysis(tasks, task_id_map, task_name_map)


def print_dependency_analysis(tasks, task_id_map, task_name_map=None):
    """Print dependency analysis in a clean format."""
    print("\n🔗 Dependency Analysis:")
    print("-" * 80)

    # If no task_name_map provided, create one
    if task_name_map is None:
        task_name_map = {str(task.id): task.name for task in tasks}

    # Find tasks with no dependencies (can start immediately)
    independent_tasks = [t for t in tasks if not t.dependencies]
    if independent_tasks:
        print("\n✨ Can start immediately:")
        for task in independent_tasks:
            tid = task_id_map[str(task.id)]
            print(f"   • {tid}: {task.name}")

    # Find tasks by dependency count
    dependent_tasks = [(t, len(t.dependencies)) for t in tasks if t.dependencies]
    if dependent_tasks:
        dependent_tasks.sort(key=lambda x: x[1])
        print("\n📊 Tasks by dependency count:")
        for task, dep_count in dependent_tasks:
            tid = task_id_map[str(task.id)]
            dep_names = [task_name_map.get(str(d), f"Unknown {str(d)[:8]}") for d in task.dependencies]
            print(f"   • {', '.join(dep_names)} → {task.name}")

    # Identify potential bottlenecks (tasks that many others depend on)
    dependency_counts = {}
    for task in tasks:
        for dep in task.dependencies:
            dep_str = str(dep)
            dependency_counts[dep_str] = dependency_counts.get(dep_str, 0) + 1

    if dependency_counts:
        bottlenecks = sorted(dependency_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        print("\n⚠️  Potential bottlenecks (tasks blocking the most others):")
        for task_id, count in bottlenecks:
            tid = task_id_map.get(task_id, task_id[:8])
            task_name = next((t.name for t in tasks if str(t.id) == task_id), "Unknown")
            print(f"   • {tid}: {task_name} (blocks {count} tasks)")

    print("-" * 80)


def create_dependency_graph(tasks, output_path):
    """Create and save task dependency graph."""
    try:
        import matplotlib.pyplot as plt
        import networkx as nx
        from networkx.drawing.nx_pydot import graphviz_layout

        G = nx.DiGraph()

        # Add nodes
        for task in tasks:
            G.add_node(str(task.id), label=task.name[:20] + "...")

        # Add edges
        for task in tasks:
            for dep in task.dependencies:
                G.add_edge(str(dep), str(task.id))

        # Create layout and draw
        plt.figure(figsize=(12, 8))
        pos = graphviz_layout(G, prog='dot') if len(G) > 1 else nx.spring_layout(G)

        nx.draw(G, pos, with_labels=True, node_color='lightblue',
                node_size=2000, font_size=8, font_weight='bold',
                arrows=True, arrowsize=20, edge_color='gray')

        plt.title("Task Dependency Graph")
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()

        print(f"\n📊 Dependency graph saved to: {output_path}")

    except ImportError as e:
        print(f"⚠️  Could not create graph: {e}")
    except Exception as e:
        print(f"⚠️  Graph creation failed: {e}")


def print_task_result(task, result, elapsed_time):
    """Print task execution result."""
    status = "📗 SUCCESS" if result.success else "📕 FAIL"
    print(f"\n{status} Task: {task.name}")
    print(f"   Runtime: {elapsed_time:.2f}s")
    print(f"   Attempts: {getattr(result, 'retry_count', 1)}")

    if hasattr(result, 'compilation_success'):
        print(f"   Syntax OK: {'✓' if result.compilation_success else '✗'}")

    if hasattr(result, 'test_results') and result.test_results:
        test_pass = result.test_results.get('passed', 0)
        test_total = result.test_results.get('total', 0)
        print(f"   Tests: {test_pass}/{test_total} passed")

        if 'coverage' in result.test_results:
            print(f"   Coverage: {result.test_results['coverage']:.1f}%")

    if not result.success and result.errors:
        print(f"   Error: {result.errors[0][:100]}...")


def print_summary_table(task_results):
    """Print ASCII summary table."""
    print("\n" + "=" * 70)
    print("┌" + "─" * 20 + "┬" + "─" * 15 + "┬" + "─" * 12 + "┬" + "─" * 15 + "┐")
    print("│ Task ID            │ Agent         │ Attempts   │ Status        │")
    print("├" + "─" * 20 + "┼" + "─" * 15 + "┼" + "─" * 12 + "┼" + "─" * 15 + "┤")

    for task_id, info in task_results.items():
        task_id_short = str(task_id)[:18]
        agent = info['agent'][:13]
        attempts = str(info['attempts'])
        status = "SUCCESS" if info['success'] else "FAILED"

        print(f"│ {task_id_short:<18} │ {agent:<13} │ {attempts:<10} │ {status:<13} │")

    print("└" + "─" * 20 + "┴" + "─" * 15 + "┴" + "─" * 12 + "┴" + "─" * 15 + "┘")


async def run_demo():
    """Run the agentic coding system demo."""
    start_time = time.time()

    # Configure logging with simple format for demo
    import logging
    logging.getLogger().setLevel(logging.WARNING)  # Suppress most logs

    # Only show important messages
    demo_logger = logging.getLogger("demo")
    demo_logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    demo_logger.addHandler(handler)

    # Initialize MetaAgent with proper projects directory
    print("🚀 Initializing MetaAgent...")
    projects_path = Path.cwd() / "projects"
    projects_path.mkdir(exist_ok=True)
    meta_agent = MetaAgent(artifact_storage_path=projects_path)

    # Initialize with a temporary context
    # The MetaAgent will create the proper project-specific context later
    from src.core.interfaces import TaskContext
    temp_context = TaskContext(project_root=projects_path)
    await meta_agent.initialize(temp_context)

    print(f"\n📝 User Request:\n{USER_REQUEST}\n")

    # Capture task decomposition
    print("🔍 Decomposing request into tasks...")

    # Process request with timeout
    task_results = {}

    try:
        # Run with timeout
        result = await asyncio.wait_for(
            meta_agent.process_request(USER_REQUEST),
            timeout=MAX_TOTAL_SECONDS
        )

        # Handle Result object
        if result.is_success():
            project_result = result.unwrap()
            tasks = project_result.tasks if hasattr(project_result, 'tasks') else []
            print("✅ Request processed successfully!")
            print(f"   Project success: {project_result.success}")
            print(f"   Tasks completed: {project_result.tasks_completed}")
            print(f"   Tasks failed: {project_result.tasks_failed}")
        else:
            print(f"❌ Request failed: {result.get_error()}")
            tasks = []

        if tasks:
            print_task_summary(tasks)
            create_dependency_graph(tasks, SHOW_GRAPH_PNG_PATH)

            # Show execution progress
            print("\n🚀 Executing tasks...")
            print("-" * 80)

        # Track results
        for task in tasks:
            task_results[task.id] = {
                'agent': task.required_role.value if task.required_role else 'meta',
                'attempts': 1,  # Would need to track retries
                'success': task.status == TaskStatus.COMPLETED
            }

        # Print results
        elapsed = time.time() - start_time
        print(f"\nTotal wall-clock: {elapsed:.2f}s")

        # Verification summary
        completed = sum(1 for r in task_results.values() if r['success'])
        total = len(task_results)
        pass_rate = (completed / total * 100) if total > 0 else 0

        print(f"Verification pass: {completed}/{total} tasks ({pass_rate:.0f}%)")

        # Summary table
        if task_results:
            print_summary_table(task_results)

        # Final status
        if pass_rate == 100:
            print("\n🎉 DEMO PASSED")
        else:
            print("\n🚨 DEMO FAILED")

            # Show top failures
            failures = [t for t in tasks if t.status != TaskStatus.COMPLETED]
            if failures:
                print("\nTop failure reasons:")
                for i, task in enumerate(failures[:3], 1):
                    print(f"{i}. {task.name}: {task.error_message or 'Unknown error'}")

    except asyncio.TimeoutError:
        print(f"\n⏰ TIMEOUT: Demo exceeded {MAX_TOTAL_SECONDS}s limit")
        return

    except Exception as e:
        print(f"\n💥 Unhandled exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc(limit=20)


async def main():
    """Main entry point."""
    print_header()

    try:
        await run_demo()
    finally:
        # No cleanup needed - projects are kept in the projects/ directory
        print("\n📁 Project artifacts are in: projects/")


if __name__ == "__main__":
    asyncio.run(main())
