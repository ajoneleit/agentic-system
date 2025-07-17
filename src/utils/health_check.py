"""System health check for the Agentic Coding System.

This module provides comprehensive health checks to ensure all components
are properly configured and can initialize correctly.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError
from structlog import get_logger

from config import ClaudeModel, Environment, get_settings, reload_settings
from src.clients.health_client import ClaudeClient
from src.core.exceptions import (
    APIError,
    APIKeyError,
    ConfigurationError,
)
from src.core.interfaces import (
    Agent,
    AgentRole,
    Artifact,
    ArtifactType,
    Task,
    TaskContext,
    TaskStatus,
)
from src.utils.config import get_config_manager, validate_api_key
from src.utils.app_logging import setup_logging


logger = get_logger(__name__)


class HealthCheckResult:
    """Result of a health check."""
    
    def __init__(self, component: str, status: str, message: str, details: Optional[Dict[str, Any]] = None):
        """Initialize health check result.
        
        Args:
            component: Name of the component checked
            status: Status (OK, WARNING, ERROR)
            message: Human-readable message
            details: Additional details
        """
        self.component = component
        self.status = status
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "component": self.component,
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }
    
    @property
    def is_healthy(self) -> bool:
        """Check if result indicates healthy status."""
        return self.status == "OK"


class SystemHealthChecker:
    """Performs comprehensive system health checks."""
    
    def __init__(self):
        """Initialize health checker."""
        self.results: List[HealthCheckResult] = []
    
    async def check_all(self) -> Dict[str, Any]:
        """Run all health checks.
        
        Returns:
            Dictionary with overall status and individual check results
        """
        self.results.clear()
        
        # Run checks in order of importance
        await self._check_python_version()
        await self._check_required_directories()
        await self._check_configuration()
        await self._check_logging()
        await self._check_api_configuration()
        await self._check_claude_connectivity()
        await self._check_interfaces()
        await self._check_dependencies()
        
        # Compile results
        return self._compile_results()
    
    async def _check_python_version(self) -> None:
        """Check Python version compatibility."""
        try:
            version = sys.version_info
            if version.major < 3 or (version.major == 3 and version.minor < 9):
                self.results.append(HealthCheckResult(
                    "python_version",
                    "ERROR",
                    f"Python 3.9+ required, found {version.major}.{version.minor}.{version.micro}",
                    {"current_version": f"{version.major}.{version.minor}.{version.micro}"}
                ))
            else:
                self.results.append(HealthCheckResult(
                    "python_version",
                    "OK",
                    f"Python {version.major}.{version.minor}.{version.micro}",
                    {"version": f"{version.major}.{version.minor}.{version.micro}"}
                ))
        except Exception as e:
            self.results.append(HealthCheckResult(
                "python_version",
                "ERROR",
                f"Failed to check Python version: {e}"
            ))
    
    async def _check_required_directories(self) -> None:
        """Check if required directories exist or can be created."""
        required_dirs = ["config", "src", "tests", "artifacts", "logs"]
        missing_dirs = []
        
        for dir_name in required_dirs:
            dir_path = Path(dir_name)
            if not dir_path.exists():
                try:
                    dir_path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    missing_dirs.append(f"{dir_name}: {e}")
        
        if missing_dirs:
            self.results.append(HealthCheckResult(
                "directories",
                "WARNING",
                "Some directories could not be created",
                {"missing": missing_dirs}
            ))
        else:
            self.results.append(HealthCheckResult(
                "directories",
                "OK",
                "All required directories present"
            ))
    
    async def _check_configuration(self) -> None:
        """Check configuration loading and validation."""
        try:
            # Try to load settings
            settings = get_settings()
            
            # Check critical settings
            if not settings.api.key:
                self.results.append(HealthCheckResult(
                    "configuration",
                    "ERROR",
                    "API key not configured",
                    {"hint": "Set ACS_API__KEY environment variable"}
                ))
                return
            
            # Validate settings
            critical_checks = [
                (settings.agent.max_parallel_agents > 0, "max_parallel_agents must be positive"),
                (settings.verification.minimum_coverage >= 0, "minimum_coverage must be non-negative"),
                (settings.api.timeout > 0, "API timeout must be positive"),
            ]
            
            failed_checks = [msg for check, msg in critical_checks if not check]
            
            if failed_checks:
                self.results.append(HealthCheckResult(
                    "configuration",
                    "WARNING",
                    "Some configuration values need attention",
                    {"issues": failed_checks}
                ))
            else:
                self.results.append(HealthCheckResult(
                    "configuration",
                    "OK",
                    "Configuration loaded successfully",
                    {
                        "environment": settings.environment.value,
                        "debug": settings.debug,
                        "version": settings.version,
                    }
                ))
                
        except ValidationError as e:
            self.results.append(HealthCheckResult(
                "configuration",
                "ERROR",
                "Configuration validation failed",
                {"errors": [err["msg"] for err in e.errors()]}
            ))
        except Exception as e:
            self.results.append(HealthCheckResult(
                "configuration",
                "ERROR",
                f"Failed to load configuration: {e}"
            ))
    
    async def _check_logging(self) -> None:
        """Check logging system initialization."""
        try:
            # Re-setup logging to test
            setup_logging()
            
            # Test logging
            test_logger = get_logger("health_check_test")
            test_logger.info("Health check test log")
            
            self.results.append(HealthCheckResult(
                "logging",
                "OK",
                "Logging system initialized"
            ))
            
        except Exception as e:
            self.results.append(HealthCheckResult(
                "logging",
                "ERROR",
                f"Logging initialization failed: {e}"
            ))
    
    async def _check_api_configuration(self) -> None:
        """Check API configuration validity."""
        try:
            settings = get_settings()
            api_key = settings.api.key.get_secret_value()
            
            # Validate API key format
            validated_key = validate_api_key(api_key)
            
            # Check API settings
            if settings.api.rate_limit_per_minute < 10:
                self.results.append(HealthCheckResult(
                    "api_config",
                    "WARNING",
                    "Rate limit seems low",
                    {"rate_limit": settings.api.rate_limit_per_minute}
                ))
            else:
                self.results.append(HealthCheckResult(
                    "api_config",
                    "OK",
                    "API configuration valid",
                    {
                        "base_url": settings.api.base_url,
                        "timeout": settings.api.timeout,
                        "rate_limit": settings.api.rate_limit_per_minute,
                    }
                ))
                
        except APIKeyError as e:
            self.results.append(HealthCheckResult(
                "api_config",
                "ERROR",
                "Invalid API key configuration",
                {"error": str(e)}
            ))
        except Exception as e:
            self.results.append(HealthCheckResult(
                "api_config",
                "ERROR",
                f"API configuration check failed: {e}"
            ))
    
    async def _check_claude_connectivity(self) -> None:
        """Check Claude API connectivity."""
        try:
            settings = get_settings()
            
            # Skip if no API key
            if not settings.api.key:
                self.results.append(HealthCheckResult(
                    "claude_api",
                    "SKIPPED",
                    "No API key configured"
                ))
                return
            
            # Create client and test with minimal request
            async with ClaudeClient() as client:
                response = await client.create_message(
                    model=ClaudeModel.HAIKU,  # Use cheapest model
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=10,
                    temperature=0,
                )
                
                if response and response.content:
                    self.results.append(HealthCheckResult(
                        "claude_api",
                        "OK",
                        "Claude API connection successful",
                        {
                            "model": response.model,
                            "tokens_used": response.usage.input_tokens + response.usage.output_tokens,
                        }
                    ))
                else:
                    self.results.append(HealthCheckResult(
                        "claude_api",
                        "ERROR",
                        "Unexpected API response format"
                    ))
                    
        except APIKeyError:
            self.results.append(HealthCheckResult(
                "claude_api",
                "ERROR",
                "Invalid API key",
                {"hint": "Check your Anthropic API key"}
            ))
        except APIError as e:
            self.results.append(HealthCheckResult(
                "claude_api",
                "ERROR",
                f"API error: {e}",
                {"error_code": e.error_code}
            ))
        except Exception as e:
            self.results.append(HealthCheckResult(
                "claude_api",
                "ERROR",
                f"Failed to connect to Claude API: {e}"
            ))
    
    async def _check_interfaces(self) -> None:
        """Check that core interfaces can be instantiated."""
        try:
            # Test creating instances
            task = Task(
                name="Health Check Task",
                description="Test task creation",
                status=TaskStatus.PENDING,
            )
            
            artifact = Artifact(
                type=ArtifactType.SOURCE_CODE,
                name="test.py",
                path=Path("test.py"),
                content="# Test",
                task_id=task.id,
                agent_id=task.id,  # Reuse for simplicity
            )
            
            context = TaskContext(
                project_root=Path("."),
                shared_memory={"test": True},
            )
            
            # Test methods
            task.mark_started()
            task.mark_completed()
            
            new_artifact = artifact.increment_version()
            
            self.results.append(HealthCheckResult(
                "interfaces",
                "OK",
                "Core interfaces working correctly",
                {
                    "task_id": str(task.id),
                    "artifact_versions": [artifact.version, new_artifact.version],
                }
            ))
            
        except Exception as e:
            self.results.append(HealthCheckResult(
                "interfaces",
                "ERROR",
                f"Interface instantiation failed: {e}"
            ))
    
    async def _check_dependencies(self) -> None:
        """Check that all required dependencies are installed."""
        missing_deps = []
        
        required_modules = [
            ("anthropic", "anthropic"),
            ("pydantic", "pydantic"),
            ("structlog", "structlog"),
            ("aiohttp", "aiohttp"),
            ("yaml", "pyyaml"),
            ("orjson", "orjson"),
            ("tenacity", "tenacity"),
            ("rich", "rich"),
        ]
        
        for module_name, package_name in required_modules:
            try:
                __import__(module_name)
            except ImportError:
                missing_deps.append(package_name)
        
        if missing_deps:
            self.results.append(HealthCheckResult(
                "dependencies",
                "ERROR",
                "Missing required dependencies",
                {
                    "missing": missing_deps,
                    "hint": f"Run: pip install {' '.join(missing_deps)}"
                }
            ))
        else:
            self.results.append(HealthCheckResult(
                "dependencies",
                "OK",
                "All required dependencies installed"
            ))
    
    def _compile_results(self) -> Dict[str, Any]:
        """Compile health check results into summary."""
        total_checks = len(self.results)
        healthy_checks = sum(1 for r in self.results if r.is_healthy)
        warnings = sum(1 for r in self.results if r.status == "WARNING")
        errors = sum(1 for r in self.results if r.status == "ERROR")
        
        overall_status = "HEALTHY"
        if errors > 0:
            overall_status = "UNHEALTHY"
        elif warnings > 0:
            overall_status = "DEGRADED"
        
        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "total_checks": total_checks,
                "healthy": healthy_checks,
                "warnings": warnings,
                "errors": errors,
            },
            "checks": [r.to_dict() for r in self.results],
        }


async def validate_system_health() -> Tuple[bool, Dict[str, Any]]:
    """Quick health check to ensure all components can initialize.
    
    Returns:
        Tuple of (is_healthy, results_dict)
    """
    checker = SystemHealthChecker()
    results = await checker.check_all()
    
    is_healthy = results["status"] == "HEALTHY"
    
    # Log results
    logger.info(
        "System health check completed",
        status=results["status"],
        summary=results["summary"],
    )
    
    # Log any errors or warnings
    for check in results["checks"]:
        if check["status"] == "ERROR":
            logger.error(
                f"Health check failed: {check['component']}",
                message=check["message"],
                details=check.get("details", {}),
            )
        elif check["status"] == "WARNING":
            logger.warning(
                f"Health check warning: {check['component']}",
                message=check["message"],
                details=check.get("details", {}),
            )
    
    return is_healthy, results


async def run_health_check_cli() -> None:
    """Run health check from command line with formatted output."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    
    console = Console()
    
    # Header
    console.print("\n[bold blue]Agentic Coding System - Health Check[/bold blue]\n")
    
    # Run checks
    with console.status("[bold green]Running system health checks..."):
        is_healthy, results = await validate_system_health()
    
    # Overall status
    status = results["status"]
    status_color = {
        "HEALTHY": "green",
        "DEGRADED": "yellow",
        "UNHEALTHY": "red",
    }.get(status, "white")
    
    console.print(Panel(
        f"[bold {status_color}]System Status: {status}[/bold {status_color}]",
        title="Overall Health",
        border_style=status_color,
    ))
    
    # Summary table
    summary = results["summary"]
    summary_table = Table(title="Summary", show_header=False)
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="white")
    
    summary_table.add_row("Total Checks", str(summary["total_checks"]))
    summary_table.add_row("[green]Healthy", f"[green]{summary['healthy']}")
    summary_table.add_row("[yellow]Warnings", f"[yellow]{summary['warnings']}")
    summary_table.add_row("[red]Errors", f"[red]{summary['errors']}")
    
    console.print(summary_table)
    
    # Detailed results
    details_table = Table(title="\nDetailed Results")
    details_table.add_column("Component", style="cyan")
    details_table.add_column("Status", style="white")
    details_table.add_column("Message", style="white")
    
    for check in results["checks"]:
        status_style = {
            "OK": "[green]✓ OK[/green]",
            "WARNING": "[yellow]⚠ WARNING[/yellow]",
            "ERROR": "[red]✗ ERROR[/red]",
            "SKIPPED": "[dim]- SKIPPED[/dim]",
        }.get(check["status"], check["status"])
        
        details_table.add_row(
            check["component"],
            status_style,
            check["message"],
        )
    
    console.print(details_table)
    
    # Show hints for errors
    errors = [c for c in results["checks"] if c["status"] == "ERROR"]
    if errors:
        console.print("\n[red]Action Required:[/red]")
        for error in errors:
            console.print(f"  • {error['component']}: {error['message']}")
            if "hint" in error.get("details", {}):
                console.print(f"    [dim]Hint: {error['details']['hint']}[/dim]")
    
    # Exit code
    exit_code = 0 if is_healthy else 1
    console.print(f"\n[dim]Exit code: {exit_code}[/dim]")
    sys.exit(exit_code)


# Note: This module should not be run directly. Use scripts/health_check.py instead.