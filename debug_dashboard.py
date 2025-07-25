#!/usr/bin/env python3
"""Debug script to test the dashboard data flow."""

import asyncio

from test_dashboard import MockCoordinator

from monitoring_dashboard import MonitoringDashboard


async def main():
    """Debug the dashboard data flow."""
    print("🔍 Debugging Dashboard Data Flow")
    print("=" * 50)

    # Create mock coordinator
    print("1. Creating mock coordinator...")
    coordinator = MockCoordinator()

    # Test get_system_status
    print("\n2. Testing get_system_status()...")
    try:
        system_status = await coordinator.get_system_status()
        print(f"✅ get_system_status() returned: {len(system_status)} keys")
        print(f"   - total_agents: {system_status.get('total_agents', 'NOT FOUND')}")
        print(f"   - agents list length: {len(system_status.get('agents', []))}")

        # Show first agent details
        agents = system_status.get('agents', [])
        if agents:
            first_agent = agents[0]
            print("\n   First agent details:")
            print(f"   - id: {first_agent.get('id', 'NOT FOUND')}")
            print(f"   - role: {first_agent.get('role', 'NOT FOUND')}")
            print(f"   - status: {first_agent.get('status', 'NOT FOUND')}")
            print(f"   - metrics keys: {list(first_agent.get('metrics', {}).keys())}")
        else:
            print("   ❌ No agents found in system_status")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test dashboard creation
    print("\n3. Testing dashboard creation...")
    try:
        dashboard = MonitoringDashboard(coordinator=coordinator)
        print("✅ Dashboard created successfully")
    except Exception as e:
        print(f"   ❌ Error creating dashboard: {e}")
        return

    # Test agent list creation
    print("\n4. Testing create_agent_list()...")
    try:
        agent_panel = await dashboard.create_agent_list()
        print("✅ Agent list panel created")
        print(f"   Panel title: {agent_panel.title}")
        print(f"   Panel type: {type(agent_panel)}")
    except Exception as e:
        print(f"   ❌ Error creating agent list: {e}")
        import traceback
        traceback.print_exc()

    # Test progress charts
    print("\n5. Testing create_progress_charts()...")
    try:
        progress_panel = await dashboard.create_progress_charts()
        print("✅ Progress charts created")
        print(f"   Panel title: {progress_panel.title}")
        print(f"   Panel type: {type(progress_panel)}")
    except Exception as e:
        print(f"   ❌ Error creating progress charts: {e}")
        import traceback
        traceback.print_exc()

    # Test system status
    print("\n6. Testing create_system_status()...")
    try:
        system_panel = await dashboard.create_system_status()
        print("✅ System status panel created")
        print(f"   Panel title: {system_panel.title}")
    except Exception as e:
        print(f"   ❌ Error creating system status: {e}")
        import traceback
        traceback.print_exc()

    print("\n✅ Debug complete!")

if __name__ == "__main__":
    asyncio.run(main())
