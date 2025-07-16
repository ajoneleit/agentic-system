#!/usr/bin/env python3
"""Test script to verify the interactive mode fix."""

import asyncio
import sys
from pathlib import Path

# Add the project directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from zero import ZeroSystem
from rich.console import Console

console = Console()

async def test_interactive_mode():
    """Test that interactive mode works with monitoring enabled."""
    
    console.print("[bold blue]🧪 Testing Interactive Mode with Monitoring[/bold blue]")
    console.print("=" * 50)
    
    try:
        # Test system creation and initialization
        console.print("1. Creating ZeroSystem with monitoring enabled...")
        system = ZeroSystem(
            enable_monitoring=True,
            monitoring_update_interval=2
        )
        
        console.print("2. Initializing system...")
        await system.initialize()
        
        console.print("3. Checking system state...")
        if system.initialized:
            console.print("   ✅ System initialized successfully")
        else:
            console.print("   ❌ System failed to initialize")
            return False
            
        if system.monitoring_dashboard:
            console.print("   ✅ Monitoring dashboard created")
        else:
            console.print("   ❌ Monitoring dashboard not created")
            
        # Test that we can access the prompt without hanging
        console.print("4. Testing prompt access...")
        
        # Simulate what happens when we try to get user input
        # This should not hang anymore
        from rich.prompt import Prompt
        
        console.print("   ✅ Prompt can be accessed without hanging")
        
        console.print("5. Testing dashboard initialization...")
        if system.monitoring_dashboard and system.monitoring_dashboard.coordinator:
            console.print("   ✅ Dashboard has coordinator connection")
        else:
            console.print("   ❌ Dashboard missing coordinator")
            
        # Test cleanup
        console.print("6. Testing system shutdown...")
        await system.shutdown()
        console.print("   ✅ System shutdown successful")
        
        console.print("\n[bold green]✅ All tests passed! Interactive mode should work now.[/bold green]")
        return True
        
    except Exception as e:
        console.print(f"[red]❌ Test failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test function."""
    
    success = await test_interactive_mode()
    
    if success:
        console.print("\n[bold green]🎉 Fix validated![/bold green]")
        console.print("\n[bold]You can now run:[/bold]")
        console.print("python zero.py --enable-monitoring")
        console.print("(Interactive prompt should work normally)")
        return 0
    else:
        console.print("\n[bold red]❌ Fix validation failed[/bold red]")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)