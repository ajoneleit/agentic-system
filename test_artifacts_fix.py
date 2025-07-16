#!/usr/bin/env python3
"""Test the artifacts fix with better debugging."""

import asyncio
import sys
from pathlib import Path

# Add the project directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from zero import ZeroSystem
from rich.console import Console

console = Console()

async def test_artifacts_fix():
    """Test the artifacts fix with better debugging."""
    
    console.print("[bold blue]🔧 Testing Artifacts Fix[/bold blue]")
    console.print("=" * 50)
    
    try:
        # Create system
        system = ZeroSystem()
        await system.initialize()
        
        console.print("✅ System initialized successfully")
        
        # Try to execute a simple task
        console.print("🔄 Running simple task...")
        
        result = await system.run_single_task("Create hello world script")
        
        console.print(f"Task completed: {result}")
        
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        
        # Check if this is our debug error
        if "Result object missing artifacts attribute" in str(e):
            console.print("✅ Debug error caught - this shows what type is being passed")
        else:
            console.print("❓ Different error")
            import traceback
            traceback.print_exc()
            
    finally:
        if 'system' in locals():
            await system.shutdown()

if __name__ == "__main__":
    asyncio.run(test_artifacts_fix())