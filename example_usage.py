#!/usr/bin/env python3
"""Example of using the Meta Agent to create a project."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.meta_agent import MetaAgent


async def create_hello_world_project():
    """Create a simple hello world project."""
    
    # Create projects directory in current folder
    projects_dir = Path("./projects")
    projects_dir.mkdir(exist_ok=True)
    
    print(f"📁 Projects directory: {projects_dir.absolute()}")
    print("="*80)
    
    # Create Meta Agent
    meta_agent = MetaAgent(artifact_storage_path=projects_dir)
    
    # Process request
    request = "Create a simple Python hello world script"
    print(f"\n📋 Request: {request}")
    
    try:
        result = await meta_agent.process_request(request)
        print(f"\n✅ Project created successfully!")
        print(f"   Success rate: {result.success_rate:.0%}")
    except Exception as e:
        print(f"\n⚠️ Project creation had some issues: {e}")
    finally:
        await meta_agent.shutdown()
    
    # Show what was created
    print("\n📂 Created projects:")
    for project in projects_dir.iterdir():
        if project.is_dir():
            print(f"\n  {project.name}/")
            workspace = project / "workspace"
            if workspace.exists():
                for file in workspace.iterdir():
                    print(f"    └── workspace/{file.name}")
    
    print(f"\n💡 Your projects are in: {projects_dir.absolute()}")
    print("   You can open this folder in Windows Explorer!")


if __name__ == "__main__":
    print("🤖 Meta Agent Project Creator")
    print("This will create a new AI project in the 'projects' folder\n")
    
    asyncio.run(create_hello_world_project())