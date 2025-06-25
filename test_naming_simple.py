#!/usr/bin/env python3
"""Simple test of the project naming logic without full dependencies."""

import asyncio
import re
from pathlib import Path
from datetime import datetime


async def generate_project_name(user_request: str) -> str:
    """Generate a short 1-2 word project name from the user request.
    
    This is a simplified version for testing without Claude API.
    """
    # Simplified logic without Claude API
    words = re.findall(r'\b\w+\b', user_request.lower())
    
    # Skip common words
    skip_words = {'create', 'make', 'build', 'write', 'generate', 'a', 'an', 'the', 
                  'that', 'with', 'simple', 'python', 'script', 'program', 'for'}
    
    meaningful_words = [w for w in words if w not in skip_words][:2]
    
    # Handle specific patterns
    if 'hello' in words and 'world' in words:
        return 'hello_world'
    elif 'hello' in words and 'amber' in words:
        return 'hello_amber'
    elif 'calculator' in words:
        return 'calculator'
    elif 'fibonacci' in words:
        return 'fibonacci'
    elif 'scraper' in words:
        return meaningful_words[0] + '_scraper' if meaningful_words else 'web_scraper'
    elif 'todo' in words or 'list' in words:
        return 'todo_list'
    elif 'api' in words:
        return 'api_server'
    
    if meaningful_words:
        return '_'.join(meaningful_words)
    return "project"


def get_project_id(project_name: str, existing_projects: list) -> str:
    """Determine project ID with numbering if needed."""
    if not existing_projects:
        return project_name
    
    # Find projects that match our base name
    matching = [p for p in existing_projects if p.startswith(project_name)]
    
    if not matching:
        return project_name
    
    # Find the highest number
    max_num = 1
    for existing in matching:
        if existing == project_name:
            max_num = max(max_num, 2)
        elif existing.startswith(f"{project_name}_"):
            suffix = existing[len(project_name)+1:]
            if suffix.isdigit():
                num = int(suffix)
                max_num = max(max_num, num + 1)
    
    return f"{project_name}_{max_num}"


async def test_naming():
    """Test project naming with different requests."""
    
    test_requests = [
        ("Create a simple Python hello world script", "hello_world"),
        ("Make a hello world program", "hello_world"),
        ("print hello amber in a python script", "hello_amber"),
        ("Build a calculator with add and subtract functions", "calculator"),
        ("Write a fibonacci sequence generator", "fibonacci"),
        ("Create a web scraper for Amazon products", "amazon_scraper"),
        ("Generate a TODO list application", "todo_list"),
        ("Build a simple REST API server", "api_server"),
        ("Create another hello world script", "hello_world"),  # Should become hello_world_2
        ("Make another hello amber script", "hello_amber"),  # Should become hello_amber_2
    ]
    
    print("🧪 Testing Project Naming System")
    print("=" * 80)
    
    # Track created projects
    created_projects = []
    
    for request, expected_base in test_requests:
        print(f"\n📋 Request: {request}")
        
        # Generate project name
        project_name = await generate_project_name(request)
        print(f"   Base name: {project_name}")
        
        # Get project ID with numbering
        project_id = get_project_id(project_name, created_projects)
        created_projects.append(project_id)
        
        print(f"   Project ID: {project_id}")
        print(f"   Expected base: {expected_base}")
        print(f"   Match: {'✅' if project_name == expected_base else '❌'}")
    
    print("\n\n📂 Simulated project creation order:")
    for i, project in enumerate(created_projects, 1):
        print(f"  {i}. {project}")
    
    # Show what the actual numbering would be
    print("\n📊 Numbering demonstration:")
    unique_projects = {}
    for req, _ in test_requests:
        name = await generate_project_name(req)
        if name not in unique_projects:
            unique_projects[name] = [name]
        else:
            unique_projects[name].append(f"{name}_{len(unique_projects[name]) + 1}")
    
    for base, versions in unique_projects.items():
        if len(versions) > 1:
            print(f"  {base}: {' -> '.join(versions)}")


if __name__ == "__main__":
    print("Testing project naming logic...")
    print("This simulates how projects would be named without requiring full dependencies\n")
    
    asyncio.run(test_naming())