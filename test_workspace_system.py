#!/usr/bin/env python3
"""Test the new workspace system with a calculator example."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.meta_agent import MetaAgent


async def test_workspace():
    """Test workspace system with calculator task."""
    
    # Task to execute
    user_request = "Create a Python calculator with add and subtract functions"
    
    print(f"📋 Task: {user_request}")
    print("="*80)
    
    # Create Meta Agent
    print("\n🤖 Initializing Meta Agent...")
    storage_path = Path("./projects")
    storage_path.mkdir(exist_ok=True)
    
    meta_agent = MetaAgent(artifact_storage_path=storage_path)
    
    try:
        print("\n🚀 Processing request...")
        result = await meta_agent.process_request(user_request)
        
        print("\n✅ Execution complete!")
        print(f"  • Success rate: {result.success_rate:.1%}")
        print(f"  • Tasks completed: {result.tasks_completed}")
        print(f"  • Tasks failed: {result.tasks_failed}")
        
        # Find the project directory
        project_dirs = [d for d in storage_path.iterdir() if d.is_dir() and "calculator" in d.name]
        if project_dirs:
            project_dir = project_dirs[0]
            workspace_dir = project_dir / "workspace"
            
            print(f"\n📁 Project: {project_dir.name}")
            print(f"📂 Workspace contents:")
            
            if workspace_dir.exists():
                for file in sorted(workspace_dir.iterdir()):
                    print(f"  • {file.name}")
                    
                # Show calculator.py if it exists
                calc_file = workspace_dir / "calculator.py"
                if calc_file.exists():
                    print(f"\n📄 {calc_file.name}:")
                    print("-" * 40)
                    print(calc_file.read_text())
                    print("-" * 40)
                    
                # Show test file if it exists
                test_files = [f for f in workspace_dir.iterdir() if f.name.startswith("test_")]
                if test_files:
                    test_file = test_files[0]
                    print(f"\n📄 {test_file.name}:")
                    print("-" * 40)
                    print(test_file.read_text()[:500] + "..." if len(test_file.read_text()) > 500 else test_file.read_text())
                    print("-" * 40)
            else:
                print("  (workspace not found)")
        else:
            print("\n⚠️ No calculator project directory found")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await meta_agent.shutdown()
        print("\n✅ Test complete!")


if __name__ == "__main__":
    print("Testing the new workspace system...")
    print("This will create a calculator project with centralized workspace\n")
    
    asyncio.run(test_workspace())