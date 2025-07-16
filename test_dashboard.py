#!/usr/bin/env python3
"""Test script for the enhanced monitoring dashboard.

This script demonstrates the fixed monitoring dashboard with simulated agent activity.
"""

import asyncio
import random
from datetime import datetime, timedelta
from uuid import uuid4

from monitoring_dashboard import MonitoringDashboard
from src.utils.enhanced_monitoring import get_monitoring_system, LogLevel


class MockCoordinator:
    """Mock coordinator for testing the dashboard."""
    
    def __init__(self):
        self.agents = {}
        self.monitoring = get_monitoring_system()
        self._generate_mock_agents()
        self._simulation_task = None
    
    def _generate_mock_agents(self):
        """Generate mock agents with various states."""
        roles = ["core_logic", "testing", "documentation", "optimization"]
        statuses = ["idle", "working", "stuck", "error"]
        
        for i in range(5):
            agent_id = str(uuid4())
            status = random.choice(statuses)
            
            # Simulate different progress levels
            if status == "working":
                progress = random.uniform(10, 95)
                operation = random.choice([
                    "code_generation", "test_execution", "documentation_writing",
                    "artifact_verification", "dependency_resolution"
                ])
            elif status == "stuck":
                progress = random.uniform(30, 70)  # Stuck mid-progress
                operation = random.choice(["code_generation", "test_execution"])
            else:
                progress = 0
                operation = "idle"
            
            self.agents[agent_id] = {
                "id": agent_id,
                "role": random.choice(roles),
                "status": status,
                "tasks": random.randint(0, 3),
                "metrics": {
                    "tasks_completed": random.randint(0, 50),
                    "tasks_failed": random.randint(0, 10),
                    "success_rate": random.uniform(0.7, 1.0),
                    "average_task_time": random.uniform(30, 300),
                    "current_operation": operation,
                    "operation_duration": random.uniform(0, 600),
                    "progress_percentage": progress,
                    "heartbeat_count": random.randint(100, 1000),
                    "last_heartbeat_age": random.uniform(0, 120),
                    "stuck_detection_count": random.randint(0, 5) if status == "stuck" else 0,
                    "recovery_attempts": random.randint(0, 3) if status == "stuck" else 0,
                    "memory_usage_mb": random.uniform(50, 500),
                    "cpu_usage_percent": random.uniform(0, 100),
                    "is_stuck": status == "stuck"
                }
            }
    
    async def get_system_status(self):
        """Return mock system status."""
        status_counts = {"idle": 0, "working": 0, "stuck": 0, "error": 0}
        
        for agent in self.agents.values():
            status_counts[agent["status"]] += 1
        
        return {
            "total_agents": len(self.agents),
            "max_agents": 20,
            "agent_status_breakdown": status_counts,
            "total_active_tasks": sum(agent["tasks"] for agent in self.agents.values()),
            "system_metrics": {
                "total_stuck_detections": sum(
                    agent["metrics"]["stuck_detection_count"] for agent in self.agents.values()
                ),
                "total_recovery_attempts": sum(
                    agent["metrics"]["recovery_attempts"] for agent in self.agents.values()
                ),
                "average_success_rate": sum(
                    agent["metrics"]["success_rate"] for agent in self.agents.values()
                ) / len(self.agents),
                "agents_with_issues": len([
                    agent for agent in self.agents.values()
                    if agent["metrics"]["stuck_detection_count"] > 0
                ])
            },
            "agents": list(self.agents.values())
        }
    
    async def simulate_activity(self):
        """Simulate ongoing agent activity."""
        while True:
            try:
                # Randomly log some activity
                agent_id = uuid4()
                await self.monitoring.log_agent_activity(
                    agent_id=agent_id,
                    event_type=random.choice([
                        "task_start", "progress_update", "task_completed",
                        "stuck_detected", "recovery_attempted"
                    ]),
                    level=random.choice(list(LogLevel)),
                    message=f"Agent {str(agent_id)[:8]} performing {random.choice(['compilation', 'testing', 'documentation'])}"
                )
                
                # Randomly update agent states
                if random.random() < 0.3:  # 30% chance to update an agent
                    agent_id = random.choice(list(self.agents.keys()))
                    agent = self.agents[agent_id]
                    
                    # Update progress for working agents
                    if agent["status"] == "working":
                        agent["metrics"]["progress_percentage"] = min(
                            100, agent["metrics"]["progress_percentage"] + random.uniform(1, 10)
                        )
                        
                        # Chance to complete task
                        if agent["metrics"]["progress_percentage"] >= 100:
                            agent["status"] = "idle"
                            agent["metrics"]["current_operation"] = "idle"
                            agent["metrics"]["progress_percentage"] = 0
                            agent["metrics"]["tasks_completed"] += 1
                    
                    # Chance for idle agents to start working
                    elif agent["status"] == "idle" and random.random() < 0.2:
                        agent["status"] = "working"
                        agent["metrics"]["current_operation"] = random.choice([
                            "code_generation", "test_execution", "documentation"
                        ])
                        agent["metrics"]["progress_percentage"] = random.uniform(0, 20)
                
                await asyncio.sleep(random.uniform(2, 8))  # Random activity interval
                
            except Exception as e:
                print(f"Simulation error: {e}")
                await asyncio.sleep(5)
    
    async def start_simulation(self):
        """Start the activity simulation."""
        self._simulation_task = asyncio.create_task(self.simulate_activity())
    
    async def stop_simulation(self):
        """Stop the activity simulation."""
        if self._simulation_task:
            self._simulation_task.cancel()
            try:
                await self._simulation_task
            except asyncio.CancelledError:
                pass


async def main():
    """Test the enhanced monitoring dashboard."""
    print("🚀 Starting Enhanced Monitoring Dashboard Test")
    print("=" * 60)
    print("This test demonstrates the fixed monitoring dashboard with:")
    print("✅ Real agent status display (active/idle/stuck states)")
    print("✅ Working keyboard commands:")
    print("   - Press 'q' to quit")
    print("   - Press 'r' to refresh (automatic)")
    print("   - Press 'c' to clear logs")
    print("✅ Real-time agent activity monitoring")
    print("=" * 60)
    print()
    
    # Create mock coordinator with simulated agents
    coordinator = MockCoordinator()
    
    # Create dashboard with real coordinator
    dashboard = MonitoringDashboard(coordinator=coordinator)
    
    try:
        # Start simulation
        await coordinator.start_simulation()
        
        # Run dashboard
        await dashboard.run()
        
    except KeyboardInterrupt:
        print("\n🛑 Test stopped by user")
    except Exception as e:
        print(f"❌ Test error: {e}")
    finally:
        await coordinator.stop_simulation()
        dashboard.stop()


if __name__ == "__main__":
    asyncio.run(main())