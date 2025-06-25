#!/usr/bin/env python3
"""Demo of the new project naming system."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.meta_agent import MetaAgent


async def demo_naming():
    """Demonstrate the new naming system with a few examples."""
    
    # Create projects directory
    projects_dir = Path("./projects")
    projects_dir.mkdir(exist_ok=True)
    
    print("🎯 Project Naming Demo")
    print("=" * 80)
    print("\nThis demo shows how projects are named with short, meaningful names.")
    print("When you create multiple projects with similar purposes, they get numbered.\n")
    
    # Test requests
    demo_requests = [
        "Create a simple hello world Python script",
        "Make another hello world program",  # Should become hello_world_2
        "Build a calculator app",
    ]
    
    # Create Meta Agent
    meta_agent = MetaAgent()
    
    try:
        for i, request in enumerate(demo_requests, 1):
            print(f"\n--- Example {i} ---")
            print(f"Request: \"{request}\"")
            
            # Process with minimal execution (just decomposition)
            print("\nProcessing...")
            
            # Decompose to show it's working
            tasks = await meta_agent.decompose_task(request)
            print(f"✅ Decomposed into {len(tasks)} tasks")
            
            # The project was already created during decomposition
            # Find the latest project
            latest_project = None
            latest_time = None
            
            for project_dir in projects_dir.iterdir():
                if project_dir.is_dir():
                    metadata_file = project_dir / "project_metadata.json"
                    if metadata_file.exists():
                        import json
                        with open(metadata_file) as f:
                            metadata = json.load(f)
                            if metadata.get("request") == request:
                                if latest_time is None or project_dir.stat().st_mtime > latest_time:
                                    latest_project = project_dir.name
                                    latest_time = project_dir.stat().st_mtime
            
            if latest_project:
                print(f"\n📁 Project created: ./projects/{latest_project}/")
            
            await asyncio.sleep(0.5)  # Small delay for readability
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await meta_agent.shutdown()
    
    # Show all created projects
    print("\n\n📂 All projects in ./projects/:")
    print("-" * 40)
    
    if projects_dir.exists():
        projects = sorted([p for p in projects_dir.iterdir() if p.is_dir()])
        if projects:
            for project in projects:
                # Read metadata if available
                metadata_file = project / "project_metadata.json"
                if metadata_file.exists():
                    import json
                    with open(metadata_file) as f:
                        metadata = json.load(f)
                        request_preview = metadata.get("request", "")[:50] + "..."
                        print(f"  • {project.name}")
                        print(f"    Request: {request_preview}")
                else:
                    print(f"  • {project.name}")
        else:
            print("  (No projects yet)")
    
    print("\n💡 Notice how duplicate requests get numbered (hello_world, hello_world_2, etc.)")


if __name__ == "__main__":
    print("Starting project naming demo...")
    print("This will create a few example projects to show the naming system.\n")
    
    asyncio.run(demo_naming())