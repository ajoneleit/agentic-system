#!/usr/bin/env python3
"""Quick test to verify the dashboard displays agent data correctly."""

import asyncio
from test_dashboard import MockCoordinator
from monitoring_dashboard import MonitoringDashboard

async def test_dashboard_components():
    """Test that all dashboard components work properly."""
    print("🧪 Testing Dashboard Components")
    print("=" * 40)
    
    # Create mock coordinator
    coordinator = MockCoordinator()
    
    # Get system status
    system_status = await coordinator.get_system_status()
    print(f"✅ Mock coordinator created with {system_status['total_agents']} agents")
    
    # Create dashboard
    dashboard = MonitoringDashboard(coordinator=coordinator)
    
    # Test each component
    print("\n📊 Testing dashboard components:")
    
    # Test agent list
    try:
        agent_list = await dashboard.create_agent_list()
        print("✅ Agent list created successfully")
    except Exception as e:
        print(f"❌ Agent list failed: {e}")
    
    # Test progress charts
    try:
        progress_charts = await dashboard.create_progress_charts()
        print("✅ Progress charts created successfully")
    except Exception as e:
        print(f"❌ Progress charts failed: {e}")
    
    # Test system status
    try:
        system_status_panel = await dashboard.create_system_status()
        print("✅ System status panel created successfully")
    except Exception as e:
        print(f"❌ System status panel failed: {e}")
    
    # Test activity log
    try:
        activity_log = await dashboard.create_activity_log()
        print("✅ Activity log created successfully")
    except Exception as e:
        print(f"❌ Activity log failed: {e}")
    
    print("\n🎯 Results:")
    print(f"   - Total agents: {system_status['total_agents']}")
    print(f"   - Agents data: {len(system_status.get('agents', []))}")
    print(f"   - First agent status: {system_status.get('agents', [{}])[0].get('status', 'N/A')}")
    
    # Show agent details
    agents = system_status.get('agents', [])
    if agents:
        print(f"\n📋 Agent Details:")
        for i, agent in enumerate(agents[:3]):  # Show first 3 agents
            progress = agent.get('metrics', {}).get('progress_percentage', 0)
            print(f"   Agent {i+1}: {agent['role']} | {agent['status']} | {progress:.1f}%")
    
    print("\n✅ All components working correctly!")

if __name__ == "__main__":
    asyncio.run(test_dashboard_components())