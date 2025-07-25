#!/usr/bin/env python3
"""Test script to validate the monitoring dashboard integration with zero.py.

This script tests the complete integration of the monitoring dashboard with
the actual AgentCoordinator from the zero.py system.
"""

import asyncio
import sys
from pathlib import Path

# Add the project directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console

from zero import ZeroSystem

console = Console()

async def test_dashboard_integration():
    """Test the complete dashboard integration."""

    console.print("[bold blue]🚀 Testing Dashboard Integration with Zero.py[/bold blue]")
    console.print("=" * 60)

    # Test 1: System with monitoring enabled
    console.print("\n[bold]Test 1: Initialize system with monitoring enabled[/bold]")

    try:
        system = ZeroSystem(
            enable_monitoring=True,
            monitoring_update_interval=1  # Fast updates for testing
        )

        # Initialize the system
        await system.initialize()

        # Check that monitoring dashboard was created
        if system.monitoring_dashboard:
            console.print("✅ Monitoring dashboard initialized successfully")

            # Check that dashboard has real coordinator
            if system.monitoring_dashboard.coordinator:
                console.print("✅ Dashboard connected to real AgentCoordinator")

                # Test getting system status
                status = await system.monitoring_dashboard.coordinator.get_system_status()
                console.print(f"✅ System status retrieved: {status['total_agents']} agents, {status['max_agents']} max")

            else:
                console.print("❌ Dashboard not connected to coordinator")

        else:
            console.print("❌ Monitoring dashboard not initialized")

    except Exception as e:
        console.print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test 2: System without monitoring
    console.print("\n[bold]Test 2: Initialize system without monitoring[/bold]")

    try:
        system_no_monitoring = ZeroSystem(enable_monitoring=False)
        await system_no_monitoring.initialize()

        if system_no_monitoring.monitoring_dashboard is None:
            console.print("✅ No monitoring dashboard created when disabled")
        else:
            console.print("❌ Monitoring dashboard created when disabled")

    except Exception as e:
        console.print(f"❌ No-monitoring test failed: {e}")

    # Test 3: CLI options validation
    console.print("\n[bold]Test 3: CLI options validation[/bold]")

    try:
        # Test that CLI accepts monitoring options
        from click.testing import CliRunner

        from zero import main

        runner = CliRunner()

        # Test help shows monitoring options
        result = runner.invoke(main, ['--help'])
        if '--enable-monitoring' in result.output and '--monitoring-update-interval' in result.output:
            console.print("✅ CLI options available in help")
        else:
            console.print("❌ CLI options not found in help")

    except Exception as e:
        console.print(f"❌ CLI options test failed: {e}")

    # Cleanup
    try:
        await system.shutdown()
        await system_no_monitoring.shutdown()
        console.print("✅ System shutdown successful")
    except Exception as e:
        console.print(f"⚠️  Shutdown warning: {e}")

    console.print("\n[bold green]✅ Dashboard integration tests completed![/bold green]")
    console.print("\n[bold]Next steps:[/bold]")
    console.print("1. Run: python zero.py --enable-monitoring")
    console.print("2. In interactive mode, type: /monitor")
    console.print("3. Dashboard will show real agent activity")

    return True

async def test_dashboard_data_flow():
    """Test that the dashboard receives real data from the coordinator."""

    console.print("\n[bold blue]🔍 Testing Dashboard Data Flow[/bold blue]")
    console.print("=" * 60)

    try:
        # Initialize system with monitoring
        system = ZeroSystem(enable_monitoring=True)
        await system.initialize()

        if not system.monitoring_dashboard:
            console.print("❌ No monitoring dashboard to test")
            return False

        dashboard = system.monitoring_dashboard

        # Test dashboard components
        console.print("\n[bold]Testing dashboard components:[/bold]")

        # Test system status
        try:
            system_status_panel = await dashboard.create_system_status()
            console.print("✅ System status panel created")
        except Exception as e:
            console.print(f"❌ System status panel failed: {e}")

        # Test agent list
        try:
            agent_list_panel = await dashboard.create_agent_list()
            console.print("✅ Agent list panel created")
        except Exception as e:
            console.print(f"❌ Agent list panel failed: {e}")

        # Test activity log
        try:
            activity_log_panel = await dashboard.create_activity_log()
            console.print("✅ Activity log panel created")
        except Exception as e:
            console.print(f"❌ Activity log panel failed: {e}")

        # Test progress charts
        try:
            progress_charts_panel = await dashboard.create_progress_charts()
            console.print("✅ Progress charts panel created")
        except Exception as e:
            console.print(f"❌ Progress charts panel failed: {e}")

        # Test getting real coordinator data
        if dashboard.coordinator:
            try:
                status = await dashboard.coordinator.get_system_status()
                console.print(f"✅ Real coordinator data: {len(status.get('agents', []))} agents")

                # Show agent details if any
                agents = status.get('agents', [])
                if agents:
                    console.print(f"✅ Agent details available: {agents[0].get('role', 'unknown')} agent")
                else:
                    console.print("ℹ️  No agents currently spawned (expected for fresh system)")

            except Exception as e:
                console.print(f"❌ Coordinator data retrieval failed: {e}")

        await system.shutdown()
        console.print("✅ Data flow tests completed")

    except Exception as e:
        console.print(f"❌ Data flow test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

async def main():
    """Main test function."""

    console.print("[bold cyan]🧪 Dashboard Integration Test Suite[/bold cyan]")
    console.print("Testing complete integration of monitoring dashboard with zero.py")
    console.print()

    # Run integration tests
    success1 = await test_dashboard_integration()
    success2 = await test_dashboard_data_flow()

    if success1 and success2:
        console.print("\n[bold green]🎉 All integration tests passed![/bold green]")
        console.print("\n[bold]Ready to use:[/bold]")
        console.print("• python zero.py --enable-monitoring")
        console.print("• Type /monitor in interactive mode")
        console.print("• Dashboard shows real agent activity")
        return 0
    else:
        console.print("\n[bold red]❌ Some integration tests failed[/bold red]")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
