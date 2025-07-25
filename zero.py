#!/usr/bin/env python3
"""/zero - Evolutionary Agentic System

An advanced agentic system that combines interaction nets, geometric evolution,
MECE decomposition, and multi-agent orchestration with an intuitive interface.

Usage:
    python zero.py                    # Interactive mode
    python zero.py "task description" # Execute single task
    python zero.py --help            # Show help
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional
from uuid import uuid4

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from structlog import get_logger

from config import get_settings
from monitoring_dashboard import MonitoringDashboard
from src.agents.evolutionary_agent import EvolutionaryAgent
from src.agents.meta_agent import MetaAgent
from src.core.interfaces import AgentRole
from src.interface.slash_commands import CommandResult, ZeroInterface

# Configure logging
logger = get_logger(__name__)
console = Console()


class ZeroSystem:
    """Main /zero system orchestrator"""

    def __init__(self, config_path: Optional[Path] = None, enable_monitoring: bool = False, monitoring_update_interval: int = 2):
        self.settings = get_settings()
        self.artifacts_path = Path("./projects")
        self.artifacts_path.mkdir(exist_ok=True)

        # Load enhanced MCP configuration
        mcp_config_path = config_path or Path("./zero-mcp-config.json")
        if mcp_config_path.exists():
            with open(mcp_config_path) as f:
                self.mcp_config = json.load(f)
        else:
            self.mcp_config = {}

        # Initialize components
        self.meta_agent = None
        self.evolution_agent = None
        self.interface = None
        self.initialized = False

        # Monitoring dashboard configuration
        self.enable_monitoring = enable_monitoring
        self.monitoring_update_interval = monitoring_update_interval
        self.monitoring_dashboard = None
        self.monitoring_task = None

    async def initialize(self):
        """Initialize all system components"""
        console.print("[bold blue]🚀 Initializing /zero System...[/bold blue]")

        try:
            # Initialize Meta Agent
            console.print("  • Creating Meta Agent...")
            self.meta_agent = MetaAgent(
                artifact_storage_path=self.artifacts_path
            )

            # Initialize Evolutionary Agent
            console.print("  • Creating Evolutionary Agent...")
            self.evolution_agent = EvolutionaryAgent(
                agent_id=uuid4(),
                role=AgentRole.CORE_LOGIC,
                artifact_storage_path=self.artifacts_path,
                evolution_enabled=True
            )

            # Initialize Interface
            console.print("  • Setting up Interface...")
            self.interface = ZeroInterface(
                meta_agent=self.meta_agent,
                evolution_agent=self.evolution_agent,
                artifacts_path=self.artifacts_path
            )

            # Verify MCP servers
            console.print("  • Checking MCP servers...")
            await self._verify_mcp_servers()

            # Initialize monitoring dashboard if enabled
            if self.enable_monitoring:
                console.print("  • Initializing monitoring dashboard...")
                await self._initialize_monitoring_dashboard()

            self.initialized = True
            console.print("[bold green]✅ /zero System Ready![/bold green]\n")

        except Exception as e:
            console.print(f"[bold red]❌ Initialization failed: {e}[/bold red]")
            raise

    async def _verify_mcp_servers(self):
        """Verify MCP server availability"""
        required_servers = [
            "sequentialthinking",
            "taskmanager",
            "context7",
            "openrouterai"
        ]

        available = []
        missing = []

        for server in required_servers:
            if server in self.mcp_config.get("mcpServers", {}):
                available.append(server)
            else:
                missing.append(server)

        if missing:
            console.print(f"[yellow]  ⚠️  Missing MCP servers: {', '.join(missing)}[/yellow]")
            console.print("     Some advanced features may be limited.")

    async def _initialize_monitoring_dashboard(self):
        """Initialize the monitoring dashboard with real coordinator."""
        try:
            # Create dashboard with real AgentCoordinator from meta_agent
            if self.meta_agent and hasattr(self.meta_agent, 'coordinator'):
                self.monitoring_dashboard = MonitoringDashboard(
                    coordinator=self.meta_agent.coordinator,
                    update_interval=self.monitoring_update_interval
                )
                console.print("    ✅ Monitoring dashboard initialized with real coordinator")
            else:
                console.print("    ⚠️  Meta agent or coordinator not available for monitoring")
        except Exception as e:
            console.print(f"    ❌ Failed to initialize monitoring dashboard: {e}")
            logger.error("Monitoring dashboard initialization failed", error=str(e))

    async def _start_monitoring_dashboard(self):
        """Start the monitoring dashboard in a separate task."""
        if not self.monitoring_dashboard:
            return

        try:
            console.print("\n[bold blue]🔍 Starting monitoring dashboard...[/bold blue]")
            console.print("Dashboard will open in a separate view")
            console.print("Press Ctrl+C to return to main system")

            # Run dashboard in a separate task
            self.monitoring_task = asyncio.create_task(
                self.monitoring_dashboard.run()
            )

            # Wait for dashboard to complete
            await self.monitoring_task

        except asyncio.CancelledError:
            console.print("\n[yellow]📊 Monitoring dashboard stopped[/yellow]")
        except Exception as e:
            console.print(f"[red]❌ Monitoring dashboard error: {e}[/red]")
            logger.error("Monitoring dashboard error", error=str(e))

    async def run_interactive(self):
        """Run in interactive mode"""
        if not self.initialized:
            await self.initialize()

        # Show welcome message
        self._show_welcome()

        # Interactive loop
        while True:
            try:
                # Get user input
                user_input = Prompt.ask("\n[bold cyan]/zero[/bold cyan]")

                if user_input.lower() in ["exit", "quit", "/exit", "/quit"]:
                    console.print("[yellow]👋 Goodbye![/yellow]")
                    break

                # Check for monitoring dashboard command
                if user_input.lower() in ["/monitor", "/dashboard", "/monitoring"]:
                    if self.monitoring_dashboard:
                        await self._start_monitoring_dashboard()
                    else:
                        console.print("[yellow]⚠️  Monitoring dashboard not enabled. Use --enable-monitoring flag.[/yellow]")
                    continue

                # Process input
                result = await self.interface.process_input(user_input)

                # Display result
                self._display_result(result)

            except KeyboardInterrupt:
                console.print("\n[yellow]Use 'exit' or Ctrl+D to quit[/yellow]")
            except EOFError:
                console.print("\n[yellow]👋 Goodbye![/yellow]")
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                logger.error("Interactive loop error", error=str(e))

    async def run_single_task(self, task: str):
        """Run a single task"""
        if not self.initialized:
            await self.initialize()

        console.print(f"[bold]Executing: {task}[/bold]\n")

        # Process task
        result = await self.interface.process_input(task)

        # Display result
        self._display_result(result)

        return result.success

    def _show_welcome(self):
        """Show welcome message"""
        monitoring_info = ""
        if self.enable_monitoring:
            monitoring_info = "\n📊 Monitoring enabled: Type [bold]/monitor[/bold] to open dashboard"

        welcome = Panel(
            f"""[bold cyan]/zero[/bold cyan] - Evolutionary Agentic System
            
🧬 Powered by interaction nets and geometric evolution
🔄 Self-improving through pattern learning
🚀 Parallel execution with MECE decomposition{monitoring_info}

Type [bold]/help[/bold] for commands or just describe what you want to build!
Type [bold]exit[/bold] to quit.""",
            title="Welcome to /zero",
            border_style="blue"
        )
        console.print(welcome)

    def _display_result(self, result: CommandResult):
        """Display command result"""
        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[red]{result.output}[/red]")

        # Show visualization if present
        if result.visualization:
            if result.visualization.startswith("<svg"):
                console.print("[dim]SVG visualization generated (not shown in terminal)[/dim]")
            else:
                # ASCII visualization
                console.print(Panel(
                    result.visualization,
                    title="Visualization",
                    border_style="blue"
                ))

        # Show suggestions if present
        if result.suggestions:
            console.print("\n[yellow]Suggestions:[/yellow]")
            for suggestion in result.suggestions:
                console.print(f"  • {suggestion}")

        # Show data summary if present
        if result.data:
            self._show_data_summary(result.data)

    def _show_data_summary(self, data: dict):
        """Show summary of result data"""
        if "partitions" in data:
            # MECE decomposition results
            table = Table(title="MECE Partitions")
            table.add_column("Partition", style="cyan")
            table.add_column("Tasks", justify="right")
            table.add_column("Compression", justify="right")
            table.add_column("Parallel Group", justify="right")

            for i, p in enumerate(data["partitions"]):
                table.add_row(
                    f"P{i+1}",
                    str(p["task_count"]),
                    f"{p['compression_ratio']:.1%}",
                    str(p["parallel_group"])
                )

            console.print(table)

        elif "evolved_state" in data:
            # Evolution results
            console.print(f"\n[dim]Evolution improved fitness by {data['improvement']:.3f}[/dim]")

        elif "results" in data and isinstance(data["results"], list):
            # Parallel execution results
            success_count = sum(1 for r in data["results"] if r["success"])
            console.print(f"\n[dim]Parallel execution: {success_count}/{len(data['results'])} successful[/dim]")

    async def shutdown(self):
        """Shutdown the system"""
        # Stop monitoring dashboard if running
        if self.monitoring_task and not self.monitoring_task.done():
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass

        if self.monitoring_dashboard:
            self.monitoring_dashboard.stop()

        if self.meta_agent:
            await self.meta_agent.shutdown()

        console.print("[dim]System shutdown complete[/dim]")


@click.command()
@click.argument('task', required=False)
@click.option('--config', type=click.Path(exists=True), help='Path to configuration file')
@click.option('--verbose', is_flag=True, help='Enable verbose output')
@click.option('--enable-monitoring', is_flag=True, help='Enable real-time monitoring dashboard')
@click.option('--monitoring-update-interval', default=2, help='Dashboard update interval in seconds')
def main(task: Optional[str], config: Optional[str], verbose: bool, enable_monitoring: bool, monitoring_update_interval: int):
    """/zero - Evolutionary Agentic System
    
    Run without arguments for interactive mode, or provide a task to execute.
    """
    # Configure logging
    import logging
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # Create system
    config_path = Path(config) if config else None
    system = ZeroSystem(
        config_path=config_path,
        enable_monitoring=enable_monitoring,
        monitoring_update_interval=monitoring_update_interval
    )

    # Run async main
    async def async_main():
        try:
            if task:
                # Single task mode
                success = await system.run_single_task(task)
                return 0 if success else 1
            else:
                # Interactive mode
                await system.run_interactive()
                return 0
        finally:
            await system.shutdown()

    # Run
    exit_code = asyncio.run(async_main())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
