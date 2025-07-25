#!/usr/bin/env python3
"""Real-time monitoring dashboard for the enhanced agent monitoring system.

This script provides a live dashboard showing agent status, progress tracking,
and system health metrics in real-time.
"""

import asyncio
import sys
import termios
import tty
from datetime import datetime, timedelta
from typing import Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text

from src.core.coordinator import AgentCoordinator
from src.utils.enhanced_monitoring import get_monitoring_system


class MonitoringDashboard:
    """Real-time monitoring dashboard for agent system."""

    def __init__(self, coordinator: Optional[AgentCoordinator] = None, update_interval: int = 2):
        self.console = Console()
        self.monitoring = get_monitoring_system()
        self.coordinator = coordinator
        self.layout = Layout()
        self.running = False
        self.clear_logs_flag = False
        self.update_interval = update_interval

        # Setup layout
        self.setup_layout()

        # Setup keyboard input (but don't set raw mode until dashboard runs)
        self.old_settings = None

    def setup_layout(self):
        """Setup the dashboard layout."""
        self.layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )

        self.layout["main"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )

        self.layout["left"].split_column(
            Layout(name="system_status", size=12),
            Layout(name="agent_list")
        )

        self.layout["right"].split_column(
            Layout(name="activity_log", size=15),
            Layout(name="progress_charts")
        )

    def create_header(self) -> Panel:
        """Create dashboard header."""
        title = Text("🚀 Enhanced Agent Monitoring Dashboard", style="bold blue")
        timestamp = Text(f"Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", style="dim")

        return Panel(
            Text.assemble(title, "\n", timestamp),
            style="blue",
            padding=(0, 1)
        )

    def create_footer(self) -> Panel:
        """Create dashboard footer."""
        help_text = Text("Press 'q' to quit | 'r' to refresh | 'c' to clear logs", style="dim")
        return Panel(help_text, style="blue", padding=(0, 1))

    async def create_system_status(self) -> Panel:
        """Create system status panel."""
        summary = await self.monitoring.get_system_summary()

        table = Table(title="System Overview", show_header=True)
        table.add_column("Metric", style="cyan", width=20)
        table.add_column("Value", style="green", width=15)
        table.add_column("Status", style="yellow", width=10)

        # System uptime
        uptime_seconds = summary["system_uptime_seconds"]
        uptime_str = str(timedelta(seconds=int(uptime_seconds)))
        table.add_row("System Uptime", uptime_str, "🟢 OK")

        # Total log entries
        total_logs = summary["total_log_entries"]
        table.add_row("Total Log Entries", str(total_logs), "📊 Active")

        # Recent activity counts
        recent_events = summary["recent_event_counts"]
        for event_type, count in recent_events.items():
            status = "🔴 Error" if "error" in event_type.lower() else "🟢 OK"
            table.add_row(f"Events: {event_type}", str(count), status)

        return Panel(table, title="System Status", border_style="green")

    async def create_agent_list(self) -> Panel:
        """Create agent list panel with real agent data."""
        table = Table(title="Active Agents", show_header=True)
        table.add_column("Agent ID", style="cyan", width=12)
        table.add_column("Role", style="magenta", width=12)
        table.add_column("Status", style="yellow", width=10)
        table.add_column("Operation", style="green", width=15)
        table.add_column("Progress", style="blue", width=8)

        if self.coordinator:
            system_status = await self.coordinator.get_system_status()
            agents = system_status.get("agents", [])

            for agent in agents:
                # Status indicators
                status_color = {
                    "idle": "🟢",
                    "working": "🟡",
                    "stuck": "🔴",
                    "error": "❌",
                    "paused": "⏸️",
                    "initializing": "🔄",
                    "shutting_down": "🛑",
                    "terminated": "💀"
                }.get(agent["status"], "⚪")

                metrics = agent.get("metrics", {})
                progress = f"{metrics.get('progress_percentage', 0):.1f}%" if metrics.get('progress_percentage', 0) > 0 else "—"
                operation = metrics.get('current_operation', 'idle')

                table.add_row(
                    agent["id"][:8] + "...",
                    agent["role"],
                    f"{status_color} {agent['status']}",
                    operation,
                    progress
                )
        else:
            table.add_row("No coordinator", "N/A", "❌ Error", "Not connected", "—")

        return Panel(table, title="Agent Status", border_style="yellow")

    async def create_activity_log(self) -> Panel:
        """Create activity log panel."""
        recent_activity = await self.monitoring.get_recent_activity(limit=10)

        table = Table(title="Recent Activity", show_header=True)
        table.add_column("Time", style="cyan", width=8)
        table.add_column("Level", style="yellow", width=7)
        table.add_column("Agent", style="magenta", width=8)
        table.add_column("Event", style="green", width=12)
        table.add_column("Message", style="white")

        for activity in recent_activity:
            level_color = {
                "info": "🟢",
                "warning": "🟡",
                "error": "🔴",
                "debug": "🔵"
            }.get(activity.level.value, "⚪")

            table.add_row(
                activity.timestamp.strftime("%H:%M:%S"),
                f"{level_color} {activity.level.value.upper()}",
                activity.agent_id[:8] + "...",
                activity.event_type,
                activity.message[:50] + "..." if len(activity.message) > 50 else activity.message
            )

        return Panel(table, title="Activity Log", border_style="blue")

    async def create_progress_charts(self) -> Panel:
        """Create progress charts panel with real agent data."""
        progress_display = []

        if self.coordinator:
            system_status = await self.coordinator.get_system_status()
            agents = system_status.get("agents", [])

            for agent in agents:
                metrics = agent.get("metrics", {})
                progress_val = metrics.get('progress_percentage', 0)

                if progress_val > 0:
                    # Create progress bar
                    progress_bar = Progress(
                        TextColumn(f"[cyan]{agent['id'][:8]}..."),
                        BarColumn(),
                        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                        expand=False
                    )

                    task = progress_bar.add_task(
                        description=metrics.get('current_operation', 'working'),
                        total=100,
                        completed=progress_val
                    )

                    progress_display.append(progress_bar)

        if not progress_display:
            content = Text("No active operations", style="dim")
        else:
            # Create a text representation of progress bars
            progress_lines = []
            for progress_bar in progress_display[:5]:  # Show max 5
                # Get the tasks from the progress bar
                tasks = list(progress_bar.tasks)
                if tasks:
                    task = tasks[0]
                    agent_id = task.description if hasattr(task, 'description') else "Unknown"
                    progress_text = f"{agent_id}: {task.percentage:.1f}%"
                    progress_lines.append(progress_text)

            content = Text("\n".join(progress_lines))

        return Panel(content, title="Progress Tracking", border_style="magenta")

    def check_keyboard_input(self) -> Optional[str]:
        """Check for keyboard input without blocking."""
        if not sys.stdin.isatty():
            return None

        try:
            import select
            # Use select to check if input is available
            if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
                key = sys.stdin.read(1)
                return key.lower() if key else None
        except ImportError:
            # Windows doesn't have select, use msvcrt
            try:
                import msvcrt
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode('utf-8')
                    return key.lower() if key else None
            except ImportError:
                pass
        except:
            pass
        return None

    def handle_keyboard_input(self, key: str) -> bool:
        """Handle keyboard input. Returns True if should continue running."""
        if key == 'q':
            return False
        elif key == 'r':
            # Force refresh (already happens automatically)
            pass
        elif key == 'c':
            self.clear_logs_flag = True
        return True

    async def update_dashboard(self):
        """Update dashboard content."""
        try:
            # Clear logs if requested
            if self.clear_logs_flag:
                await self.monitoring.clear_logs()
                self.clear_logs_flag = False

            # Update layout components
            self.layout["header"].update(self.create_header())
            self.layout["footer"].update(self.create_footer())
            self.layout["system_status"].update(await self.create_system_status())
            self.layout["agent_list"].update(await self.create_agent_list())
            self.layout["activity_log"].update(await self.create_activity_log())
            self.layout["progress_charts"].update(await self.create_progress_charts())

        except Exception as e:
            error_panel = Panel(
                f"Error updating dashboard: {str(e)}",
                title="Error",
                border_style="red"
            )
            self.layout["main"].update(error_panel)

    async def run(self):
        """Run the monitoring dashboard."""
        self.running = True

        # Setup terminal for raw input only when dashboard runs
        if sys.stdin.isatty():
            self.old_settings = termios.tcgetattr(sys.stdin)
            tty.setraw(sys.stdin.fileno())

        with Live(self.layout, console=self.console, refresh_per_second=1) as live:
            while self.running:
                # Check for keyboard input
                key = self.check_keyboard_input()
                if key:
                    if not self.handle_keyboard_input(key):
                        break

                await self.update_dashboard()
                await asyncio.sleep(self.update_interval)  # Configurable update interval

    def stop(self):
        """Stop the dashboard."""
        self.running = False

        # Restore terminal settings
        if self.old_settings and sys.stdin.isatty():
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)


async def main():
    """Main function to run the monitoring dashboard."""
    # For now, run without coordinator since we don't have one instantiated
    # In a real system, you'd pass the coordinator instance here
    dashboard = MonitoringDashboard()

    try:
        await dashboard.run()
    except KeyboardInterrupt:
        dashboard.stop()
        print("\n🛑 Dashboard stopped by user")
    except Exception as e:
        print(f"❌ Dashboard error: {e}")
    finally:
        dashboard.stop()


if __name__ == "__main__":
    asyncio.run(main())
