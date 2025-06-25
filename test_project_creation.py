#!/usr/bin/env python3
"""Test project creation in a proper directory structure."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.meta_agent import MetaAgent


async def test_project_creation():
    """Test creating a project with proper directory structure."""
    
    # Task to execute
    user_request = "Create a Python script that prints hello world"
    
    print(f"📋 Task: {user_request}")
    print("="*80)
    
    # Create projects directory in current folder
    projects_dir = Path("./projects")
    projects_dir.mkdir(exist_ok=True)
    
    print(f"\n📁 Projects will be created in: {projects_dir.absolute()}")
    
    # Create Meta Agent with proper projects directory
    meta_agent = MetaAgent(artifact_storage_path=projects_dir)
    
    try:
        print("\n🚀 Processing request...")
        result = await meta_agent.process_request(user_request)
        
        print("\n✅ Execution complete!")
        print(f"  • Success rate: {result.success_rate:.1%}")
        print(f"  • Tasks completed: {result.tasks_completed}")
        
        # Show created project structure
        print("\n📂 Created project structure:")
        for project_dir in sorted(projects_dir.iterdir()):
            if project_dir.is_dir() and "hello" in project_dir.name.lower():
                print(f"\n{project_dir.name}/")
                
                # Show structure
                for item in sorted(project_dir.rglob("*")):
                    relative_path = item.relative_to(project_dir)
                    indent = "  " * len(relative_path.parts)
                    if item.is_dir():
                        print(f"{indent}{item.name}/")
                    else:
                        print(f"{indent}{item.name}")
                
                # Show workspace contents
                workspace = project_dir / "workspace"
                if workspace.exists():
                    print(f"\n📄 Files in workspace:")
                    for file in workspace.iterdir():
                        if file.is_file():
                            print(f"\n--- {file.name} ---")
                            content = file.read_text()
                            print(content if len(content) < 500 else content[:500] + "\n...")
                            print("---")
                
                break
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await meta_agent.shutdown()
        print("\n✅ Test complete!")
        print(f"\n💡 Check the folder: {projects_dir.absolute()}")


if __name__ == "__main__":
    print("Testing project creation with proper directory structure...")
    print("Projects will be created in the current directory under 'projects'\n")
    
    asyncio.run(test_project_creation())