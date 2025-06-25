#!/usr/bin/env python3
"""Test the new project naming system."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.meta_agent import MetaAgent


async def test_naming():
    """Test project naming with different requests."""
    
    test_requests = [
        "Create a simple Python hello world script",
        "Make a hello world program",
        "Build a calculator with add and subtract functions",
        "Write a fibonacci sequence generator",
        "Create a web scraper for Amazon products",
        "Generate a TODO list application",
        "Build a simple REST API server",
        "Create another hello world script",  # Should be hello_world_2
    ]
    
    print("🧪 Testing Project Naming System")
    print("=" * 80)
    
    # Create Meta Agent
    meta_agent = MetaAgent()
    
    try:
        for request in test_requests:
            print(f"\n📋 Request: {request}")
            
            # Just test the naming without full execution
            project_name = await meta_agent._generate_project_name(request)
            print(f"   Generated name: {project_name}")
            
            # Simulate project creation to test numbering
            project_id = await meta_agent._initialize_project_storage(request)
            print(f"   Project ID: {project_id}")
            print(f"   Location: ./projects/{project_id}/")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await meta_agent.shutdown()
        
    print("\n\n📂 Created projects:")
    projects_dir = Path("./projects")
    if projects_dir.exists():
        for project in sorted(projects_dir.iterdir()):
            if project.is_dir():
                print(f"  - {project.name}")


if __name__ == "__main__":
    print("Testing new project naming system...")
    print("This will create project folders with short, meaningful names\n")
    
    asyncio.run(test_naming())