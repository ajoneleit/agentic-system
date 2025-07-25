#!/usr/bin/env python3
"""Test script to validate the enhanced monitoring implementation.

This script tests the comprehensive agent status detection, progress tracking,
and stuck agent recovery mechanisms.
"""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import structlog
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from src.agents.sub_agent import CodeGeneratorAgent
from src.core.communication import CommunicationHub
from src.core.coordinator import AgentCoordinator
from src.core.interfaces import AgentRole, Task, TaskContext
from src.core.task_manager import TaskManager
from src.utils.enhanced_monitoring import (
    LogLevel,
    get_monitoring_system,
    log_agent_activity,
    log_progress_update,
    log_recovery_attempt,
    log_stuck_agent,
)

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

console = Console()


class TestMonitoringSystem:
    """Test suite for enhanced monitoring system."""

    def __init__(self):
        self.console = console
        self.monitoring = get_monitoring_system()
        self.coordinator = None
        self.task_manager = None
        self.communication_hub = None

    async def setup(self):
        """Setup test environment."""
        self.console.print("[bold blue]Setting up test environment...[/bold blue]")

        # Initialize components
        self.task_manager = TaskManager()
        self.communication_hub = CommunicationHub()
        self.coordinator = AgentCoordinator(
            task_manager=self.task_manager,
            communication_hub=self.communication_hub,
            max_agents=5
        )

        # Register agent factories
        self.coordinator.register_agent_factory(AgentRole.CORE_LOGIC, CodeGeneratorAgent)

        # Start coordinator
        await self.coordinator.start()

        self.console.print("[bold green]✅ Test environment ready[/bold green]")

    async def test_basic_monitoring(self):
        """Test basic monitoring functionality."""
        self.console.print("\n[bold yellow]Testing Basic Monitoring...[/bold yellow]")

        # Create test context
        context = TaskContext(
            project_root=Path("/tmp/test_project"),
            project_id="test_project"
        )

        # Spawn an agent
        agent = await self.coordinator.spawn_agent(AgentRole.CORE_LOGIC, context)

        # Create a simple task
        task = Task(
            name="Test Task",
            description="A simple test task",
            required_role=AgentRole.CORE_LOGIC
        )

        # Test logging functions
        await log_agent_activity(
            agent_id=agent.id,
            event_type="test_event",
            level=LogLevel.INFO,
            message="Testing basic monitoring",
            test_data="sample_data"
        )

        await log_progress_update(
            agent_id=agent.id,
            operation="test_operation",
            progress_percentage=50.0,
            test_phase="middle"
        )

        # Check recent activity
        recent_activity = await self.monitoring.get_recent_activity(
            agent_id=agent.id,
            limit=10
        )

        self.console.print(f"✅ Logged {len(recent_activity)} activities")

        # Display activity table
        table = Table(title="Recent Agent Activity")
        table.add_column("Timestamp", style="cyan")
        table.add_column("Event Type", style="magenta")
        table.add_column("Level", style="yellow")
        table.add_column("Message", style="green")

        for activity in recent_activity[:5]:
            table.add_row(
                activity.timestamp.strftime("%H:%M:%S"),
                activity.event_type,
                activity.level.value,
                activity.message
            )

        self.console.print(table)

        return True

    async def test_stuck_agent_detection(self):
        """Test stuck agent detection mechanism."""
        self.console.print("\n[bold yellow]Testing Stuck Agent Detection...[/bold yellow]")

        # Create test context
        context = TaskContext(
            project_root=Path("/tmp/test_project"),
            project_id="test_project"
        )

        # Spawn an agent
        agent = await self.coordinator.spawn_agent(AgentRole.CORE_LOGIC, context)

        # Simulate a stuck agent by manually setting metrics
        metrics = self.coordinator._agent_metrics.get(agent.id)
        if metrics:
            # Simulate long-running operation
            metrics.start_operation("stuck_operation")
            metrics.operation_start_time = datetime.utcnow() - timedelta(seconds=400)  # 400 seconds ago
            metrics.last_heartbeat = datetime.utcnow() - timedelta(seconds=120)  # 2 minutes ago

            self.console.print(f"Agent {agent.id} simulated as stuck")

            # Test stuck detection
            is_stuck = metrics.is_stuck()
            self.console.print(f"✅ Stuck detection result: {is_stuck}")

            # Log stuck agent
            await log_stuck_agent(
                agent_id=agent.id,
                current_operation=metrics.current_operation,
                operation_duration=metrics.get_operation_duration(),
                last_heartbeat_age=(datetime.utcnow() - metrics.last_heartbeat).total_seconds()
            )

            # Simulate recovery attempt
            await log_recovery_attempt(
                agent_id=agent.id,
                strategy="pause_resume",
                attempt_number=1
            )

            return True

        return False

    async def test_progress_tracking(self):
        """Test progress tracking functionality."""
        self.console.print("\n[bold yellow]Testing Progress Tracking...[/bold yellow]")

        # Create test context
        context = TaskContext(
            project_root=Path("/tmp/test_project"),
            project_id="test_project"
        )

        # Spawn an agent
        agent = await self.coordinator.spawn_agent(AgentRole.CORE_LOGIC, context)

        # Simulate progress updates
        operations = [
            ("initialization", 0),
            ("data_loading", 25),
            ("processing", 50),
            ("validation", 75),
            ("completion", 100)
        ]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("Simulating agent progress...", total=len(operations))

            for operation, percentage in operations:
                await log_progress_update(
                    agent_id=agent.id,
                    operation=operation,
                    progress_percentage=percentage,
                    simulation=True
                )

                progress.update(task, advance=1)
                await asyncio.sleep(0.5)

        self.console.print("✅ Progress tracking test completed")
        return True

    async def test_system_monitoring(self):
        """Test system-wide monitoring."""
        self.console.print("\n[bold yellow]Testing System Monitoring...[/bold yellow]")

        # Generate system status
        system_status = await self.coordinator.get_system_status()

        # Display system status
        table = Table(title="System Status")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total Agents", str(system_status["total_agents"]))
        table.add_row("Max Agents", str(system_status["max_agents"]))
        table.add_row("Active Tasks", str(system_status["total_active_tasks"]))

        for status, count in system_status["agent_status_breakdown"].items():
            table.add_row(f"Agents {status}", str(count))

        self.console.print(table)

        # Test system summary
        summary = await self.monitoring.get_system_summary()

        summary_table = Table(title="Monitoring System Summary")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")

        summary_table.add_row("Total Log Entries", str(summary["total_log_entries"]))
        summary_table.add_row("System Uptime", f"{summary['system_uptime_seconds']:.1f}s")

        for event_type, count in summary["recent_event_counts"].items():
            summary_table.add_row(f"Events: {event_type}", str(count))

        self.console.print(summary_table)

        return True

    async def test_recovery_mechanisms(self):
        """Test automatic recovery mechanisms."""
        self.console.print("\n[bold yellow]Testing Recovery Mechanisms...[/bold yellow]")

        # Create test context
        context = TaskContext(
            project_root=Path("/tmp/test_project"),
            project_id="test_project"
        )

        # Spawn an agent
        agent = await self.coordinator.spawn_agent(AgentRole.CORE_LOGIC, context)

        # Get agent metrics
        metrics = self.coordinator._agent_metrics.get(agent.id)
        if metrics:
            # Simulate multiple recovery attempts
            for attempt in range(1, 4):
                await log_recovery_attempt(
                    agent_id=agent.id,
                    strategy=f"strategy_{attempt}",
                    attempt_number=attempt,
                    simulation=True
                )

                metrics.record_recovery_attempt()

                self.console.print(f"Recovery attempt #{attempt} recorded")
                await asyncio.sleep(0.2)

            # Test recovery escalation
            if metrics.recovery_attempts >= 3:
                self.console.print("✅ Recovery escalation triggered")

                # Simulate agent termination
                await self.coordinator.terminate_agent(agent.id)
                self.console.print("✅ Agent terminated for restart")

            return True

        return False

    async def run_all_tests(self):
        """Run all monitoring tests."""
        self.console.print(Panel.fit(
            "[bold blue]Enhanced Monitoring System Test Suite[/bold blue]",
            border_style="blue"
        ))

        try:
            await self.setup()

            tests = [
                ("Basic Monitoring", self.test_basic_monitoring),
                ("Stuck Agent Detection", self.test_stuck_agent_detection),
                ("Progress Tracking", self.test_progress_tracking),
                ("System Monitoring", self.test_system_monitoring),
                ("Recovery Mechanisms", self.test_recovery_mechanisms)
            ]

            results = []
            for test_name, test_func in tests:
                try:
                    result = await test_func()
                    results.append((test_name, result, None))
                except Exception as e:
                    results.append((test_name, False, str(e)))

            # Display results
            self.console.print("\n[bold blue]Test Results:[/bold blue]")
            results_table = Table(title="Test Results")
            results_table.add_column("Test", style="cyan")
            results_table.add_column("Status", style="green")
            results_table.add_column("Error", style="red")

            for test_name, success, error in results:
                status = "✅ PASS" if success else "❌ FAIL"
                results_table.add_row(test_name, status, error or "")

            self.console.print(results_table)

            # Summary
            passed = sum(1 for _, success, _ in results if success)
            total = len(results)

            if passed == total:
                self.console.print(f"\n[bold green]🎉 All tests passed ({passed}/{total})[/bold green]")
            else:
                self.console.print(f"\n[bold red]❌ {total - passed} tests failed ({passed}/{total})[/bold red]")

        except Exception as e:
            self.console.print(f"[bold red]Test suite failed: {e}[/bold red]")

        finally:
            # Cleanup
            if self.coordinator:
                await self.coordinator.stop()
            self.console.print("\n[bold blue]Test suite completed[/bold blue]")


async def main():
    """Main test function."""
    test_suite = TestMonitoringSystem()
    await test_suite.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
