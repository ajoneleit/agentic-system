#!/usr/bin/env python3
"""Demo task decomposition with mocked responses to show the format."""

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.interfaces import Task, TaskPriority, AgentRole, TaskStatus


def create_sample_decomposition(user_request: str):
    """Create a sample task decomposition for demonstration."""
    
    # Example decompositions for different requests
    if "calculator" in user_request.lower():
        return {
            "tasks": [
                {
                    "name": "Design Calculator Interface",
                    "description": "Define the Calculator class structure with methods for basic operations",
                    "required_role": "core_logic",
                    "estimated_complexity": "low",
                    "priority": "high",
                    "dependencies": []
                },
                {
                    "name": "Implement Addition Function",
                    "description": "Create the add() method that takes two numbers and returns their sum",
                    "required_role": "core_logic",
                    "estimated_complexity": "low",
                    "priority": "high",
                    "dependencies": ["Design Calculator Interface"]
                },
                {
                    "name": "Implement Subtraction Function",
                    "description": "Create the subtract() method that takes two numbers and returns their difference",
                    "required_role": "core_logic",
                    "estimated_complexity": "low",
                    "priority": "high",
                    "dependencies": ["Design Calculator Interface"]
                },
                {
                    "name": "Write Unit Tests",
                    "description": "Create comprehensive unit tests for add() and subtract() methods",
                    "required_role": "testing",
                    "estimated_complexity": "medium",
                    "priority": "high",
                    "dependencies": ["Implement Addition Function", "Implement Subtraction Function"]
                },
                {
                    "name": "Generate API Documentation",
                    "description": "Create documentation for the Calculator class and its methods",
                    "required_role": "documentation",
                    "estimated_complexity": "low",
                    "priority": "medium",
                    "dependencies": ["Design Calculator Interface"]
                }
            ]
        }
    
    elif "web scraper" in user_request.lower():
        return {
            "tasks": [
                {
                    "name": "Analyze Target Website Structure",
                    "description": "Examine the HTML structure of the e-commerce site to identify product price elements",
                    "required_role": "core_logic",
                    "estimated_complexity": "medium",
                    "priority": "high",
                    "dependencies": []
                },
                {
                    "name": "Implement HTTP Request Handler",
                    "description": "Create functions to fetch web pages with proper headers and error handling",
                    "required_role": "core_logic",
                    "estimated_complexity": "medium",
                    "priority": "high",
                    "dependencies": []
                },
                {
                    "name": "Create HTML Parser",
                    "description": "Implement BeautifulSoup-based parser to extract product information and prices",
                    "required_role": "core_logic",
                    "estimated_complexity": "high",
                    "priority": "high",
                    "dependencies": ["Analyze Target Website Structure"]
                },
                {
                    "name": "Implement Data Storage",
                    "description": "Create data models and storage mechanism for scraped product data",
                    "required_role": "core_logic",
                    "estimated_complexity": "medium",
                    "priority": "medium",
                    "dependencies": ["Create HTML Parser"]
                },
                {
                    "name": "Add Rate Limiting",
                    "description": "Implement rate limiting to avoid overloading the target server",
                    "required_role": "optimization",
                    "estimated_complexity": "medium",
                    "priority": "high",
                    "dependencies": ["Implement HTTP Request Handler"]
                },
                {
                    "name": "Write Integration Tests",
                    "description": "Create tests for the complete scraping workflow",
                    "required_role": "testing",
                    "estimated_complexity": "high",
                    "priority": "medium",
                    "dependencies": ["Create HTML Parser", "Implement Data Storage"]
                },
                {
                    "name": "Create Usage Documentation",
                    "description": "Write documentation on how to use the scraper and configure it for different sites",
                    "required_role": "documentation",
                    "estimated_complexity": "medium",
                    "priority": "low",
                    "dependencies": ["Create HTML Parser", "Implement Data Storage"]
                }
            ]
        }
    
    else:
        # Generic decomposition
        return {
            "tasks": [
                {
                    "name": "Analyze Requirements",
                    "description": f"Break down the requirements for: {user_request}",
                    "required_role": "core_logic",
                    "estimated_complexity": "medium",
                    "priority": "high",
                    "dependencies": []
                },
                {
                    "name": "Implement Core Functionality",
                    "description": "Create the main implementation based on requirements",
                    "required_role": "core_logic",
                    "estimated_complexity": "high",
                    "priority": "high",
                    "dependencies": ["Analyze Requirements"]
                },
                {
                    "name": "Write Tests",
                    "description": "Create unit and integration tests",
                    "required_role": "testing",
                    "estimated_complexity": "medium",
                    "priority": "high",
                    "dependencies": ["Implement Core Functionality"]
                },
                {
                    "name": "Create Documentation",
                    "description": "Generate user and API documentation",
                    "required_role": "documentation",
                    "estimated_complexity": "low",
                    "priority": "medium",
                    "dependencies": ["Implement Core Functionality"]
                }
            ]
        }


def convert_to_task_objects(task_dicts):
    """Convert task dictionaries to Task objects."""
    tasks = []
    name_to_task = {}
    
    # First pass: create all tasks
    for task_dict in task_dicts:
        task = Task(
            id=uuid4(),
            name=task_dict["name"],
            description=task_dict["description"],
            priority=TaskPriority[task_dict["priority"].upper()],
            required_role=AgentRole(task_dict["required_role"]) if task_dict.get("required_role") else None,
            estimated_complexity=task_dict["estimated_complexity"],
            status=TaskStatus.PENDING,
            created_at=datetime.utcnow(),
            metadata={
                "generated_by": "demo_decomposition",
                "original_request": task_dict.get("original_request", "")
            },
            tags=set([task_dict["required_role"], task_dict["priority"]])
        )
        tasks.append(task)
        name_to_task[task.name] = task
    
    # Second pass: set dependencies
    for task, task_dict in zip(tasks, task_dicts):
        for dep_name in task_dict.get("dependencies", []):
            if dep_name in name_to_task:
                task.dependencies.append(name_to_task[dep_name].id)
    
    return tasks


def analyze_dependencies(tasks):
    """Create dependency map from tasks."""
    dependencies = {}
    
    for task in tasks:
        dependencies[str(task.id)] = [str(dep_id) for dep_id in task.dependencies]
    
    return dependencies


def print_task_details(task, index):
    """Print detailed task information."""
    print(f"\n{'='*60}")
    print(f"📌 SUBTASK {index}: {task.name}")
    print(f"{'='*60}")
    
    print(f"\n📝 Description:")
    print(f"   {task.description}")
    
    print(f"\n🔧 Properties:")
    print(f"   • ID: {task.id}")
    print(f"   • Role: {task.required_role.value if task.required_role else 'Any'}")
    print(f"   • Priority: {task.priority.value}")
    print(f"   • Complexity: {task.estimated_complexity}")
    print(f"   • Status: {task.status.value}")
    
    if task.dependencies:
        print(f"\n🔗 Dependencies: {len(task.dependencies)}")
    else:
        print(f"\n🔗 Dependencies: None (can start immediately)")
    
    if task.tags:
        print(f"\n🏷️  Tags: {', '.join(task.tags)}")
    
    # Show JSON representation
    task_json = {
        "id": str(task.id),
        "name": task.name,
        "description": task.description,
        "required_role": task.required_role.value if task.required_role else None,
        "priority": task.priority.value,
        "status": task.status.value,
        "estimated_complexity": task.estimated_complexity,
        "dependencies": [str(dep) for dep in task.dependencies],
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "metadata": task.metadata,
        "tags": list(task.tags) if task.tags else []
    }
    
    print(f"\n📄 JSON Representation:")
    print(json.dumps(task_json, indent=2))


def main():
    """Run the demo."""
    print("="*80)
    print("🤖 META AGENT TASK DECOMPOSITION DEMO")
    print("="*80)
    print("\nThis demo shows how the Meta Agent decomposes tasks into subtasks.")
    print("(Using mocked responses for demonstration - no API calls)\n")
    
    # Get user input
    print("Enter a task description, or choose from examples:")
    print("1. Create a simple calculator with add and subtract functions")
    print("2. Create a Python web scraper that extracts product prices from an e-commerce website")
    print("3. Enter your own task")
    
    choice = input("\nYour choice (1-3): ").strip()
    
    if choice == "1":
        user_request = "Create a simple calculator with add and subtract functions"
    elif choice == "2":
        user_request = "Create a Python web scraper that extracts product prices from an e-commerce website"
    else:
        user_request = input("Enter your task: ").strip()
        if not user_request:
            user_request = "Create a REST API with user authentication"
    
    print(f"\n📋 USER REQUEST: {user_request}")
    print("="*80)
    
    # Generate decomposition
    print("\n🔍 DECOMPOSING TASK...")
    print("(In real usage, this would call Claude Opus)\n")
    
    decomposition = create_sample_decomposition(user_request)
    tasks = convert_to_task_objects(decomposition["tasks"])
    
    print(f"✅ Decomposed into {len(tasks)} subtasks\n")
    
    # Show each task in detail
    for i, task in enumerate(tasks, 1):
        print_task_details(task, i)
    
    # Show dependency analysis
    print("\n\n" + "="*80)
    print("🔗 DEPENDENCY ANALYSIS")
    print("="*80)
    
    dependencies = analyze_dependencies(tasks)
    
    # Create dependency visualization
    print("\nDependency Graph:")
    for task in tasks:
        deps = [t.name for t in tasks if t.id in task.dependencies]
        if deps:
            print(f"\n'{task.name}'")
            for dep in deps:
                print(f"  ← depends on '{dep}'")
        else:
            print(f"\n'{task.name}' (no dependencies - can start immediately)")
    
    # Show execution order
    print("\n\n" + "="*80)
    print("📊 EXECUTION PLAN")
    print("="*80)
    
    # Determine execution order (topological sort)
    execution_order = []
    completed = set()
    
    while len(completed) < len(tasks):
        for task in tasks:
            if task.id in completed:
                continue
            
            # Check if all dependencies are completed
            if all(dep_id in completed for dep_id in task.dependencies):
                execution_order.append(task)
                completed.add(task.id)
    
    print("\nTasks would be executed in this order:")
    for i, task in enumerate(execution_order, 1):
        deps_count = len(task.dependencies)
        print(f"\n{i}. {task.name}")
        print(f"   Role: {task.required_role.value if task.required_role else 'Any'}")
        print(f"   Can start: {'Immediately' if deps_count == 0 else f'After {deps_count} dependencies complete'}")
    
    # Show parallel execution opportunities
    print("\n\n" + "="*80)
    print("⚡ PARALLEL EXECUTION OPPORTUNITIES")
    print("="*80)
    
    # Group tasks by when they can start
    levels = []
    completed = set()
    remaining = set(task.id for task in tasks)
    
    while remaining:
        # Find tasks that can start now
        current_level = []
        for task in tasks:
            if task.id not in remaining:
                continue
            if all(dep_id in completed for dep_id in task.dependencies):
                current_level.append(task)
        
        if current_level:
            levels.append(current_level)
            for task in current_level:
                completed.add(task.id)
                remaining.remove(task.id)
        else:
            break
    
    for i, level in enumerate(levels, 1):
        print(f"\nStage {i}: {len(level)} task(s) can run in parallel")
        for task in level:
            print(f"  • {task.name} ({task.required_role.value if task.required_role else 'Any'})")
    
    # Summary
    print("\n\n" + "="*80)
    print("📊 SUMMARY")
    print("="*80)
    
    role_counts = {}
    for task in tasks:
        role = task.required_role.value if task.required_role else "any"
        role_counts[role] = role_counts.get(role, 0) + 1
    
    print(f"\nTotal subtasks: {len(tasks)}")
    print(f"Execution stages: {len(levels)}")
    print(f"Maximum parallelism: {max(len(level) for level in levels)} tasks")
    
    print("\nTasks by role:")
    for role, count in sorted(role_counts.items()):
        print(f"  • {role}: {count} task(s)")
    
    print("\n✅ Demo complete!")
    print("\nIn actual usage:")
    print("• Claude Opus would generate the task decomposition")
    print("• Sub-agents would use Claude CLI to implement each task")
    print("• The Meta Agent would coordinate execution and handle failures")


if __name__ == "__main__":
    main()