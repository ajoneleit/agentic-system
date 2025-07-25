#!/usr/bin/env python3
"""Maintenance Scheduler - Automated maintenance and validation scheduling.

This module provides scheduled maintenance tasks to ensure continuous
compliance with the three guiding principles.
"""

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import schedule


class MaintenanceType(Enum):
    """Types of maintenance tasks."""

    DOCUMENTATION_VALIDATION = "documentation_validation"
    REALITY_CHECK = "reality_check"
    METRICS_VALIDATION = "metrics_validation"
    QUALITY_GATES = "quality_gates"
    DEPENDENCY_UPDATE = "dependency_update"
    CLEANUP = "cleanup"


@dataclass
class MaintenanceTask:
    """A scheduled maintenance task."""

    name: str
    task_type: MaintenanceType
    command: list[str]
    schedule_interval: str  # 'daily', 'weekly', 'hourly'
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    success_count: int = 0
    failure_count: int = 0
    enabled: bool = True


@dataclass
class MaintenanceResult:
    """Result of a maintenance task execution."""

    task_name: str
    success: bool
    start_time: datetime
    end_time: datetime
    output: str
    error_output: str
    exit_code: int


class MaintenanceScheduler:
    """Schedules and executes automated maintenance tasks."""

    def __init__(self, project_root: Path = None):
        """Initialize maintenance scheduler."""
        self.project_root = project_root or Path.cwd()
        self.maintenance_log = self.project_root / "docs" / "metrics" / "maintenance.log"
        self.maintenance_log.parent.mkdir(parents=True, exist_ok=True)

        # Define maintenance tasks
        self.tasks = self._define_maintenance_tasks()

    def _define_maintenance_tasks(self) -> list[MaintenanceTask]:
        """Define all maintenance tasks."""
        return [
            MaintenanceTask(
                name="Daily Documentation Validation",
                task_type=MaintenanceType.DOCUMENTATION_VALIDATION,
                command=[
                    sys.executable,
                    "docs/validation/doc_validator.py",
                    "--check-code-refs",
                    "--test-examples",
                    "--check-completeness",
                ],
                schedule_interval="daily",
            ),
            MaintenanceTask(
                name="Daily Reality Check",
                task_type=MaintenanceType.REALITY_CHECK,
                command=[
                    sys.executable,
                    "docs/validation/reality_checker.py",
                    "--check-all",
                    "--save-report",
                    "docs/metrics/daily-reality-check.json",
                ],
                schedule_interval="daily",
            ),
            MaintenanceTask(
                name="Daily Metrics Validation",
                task_type=MaintenanceType.METRICS_VALIDATION,
                command=[
                    sys.executable,
                    "docs/validation/metrics_validator.py",
                    "--validate-all",
                    "--save-history",
                ],
                schedule_interval="daily",
            ),
            MaintenanceTask(
                name="Hourly Quality Gates Check",
                task_type=MaintenanceType.QUALITY_GATES,
                command=[sys.executable, "docs/validation/quality_gates.py", "--ci", "--report"],
                schedule_interval="hourly",
            ),
            MaintenanceTask(
                name="Weekly Documentation Cleanup",
                task_type=MaintenanceType.CLEANUP,
                command=[
                    sys.executable,
                    "-c",
                    "import shutil; "
                    "from pathlib import Path; "
                    "metrics_dir = Path('docs/metrics'); "
                    "old_files = [f for f in metrics_dir.glob('*-ci.json') "
                    "if f.stat().st_mtime < (time.time() - 7*24*3600)]; "
                    "[f.unlink() for f in old_files]; "
                    "print(f'Cleaned up {len(old_files)} old metric files')",
                ],
                schedule_interval="weekly",
            ),
            MaintenanceTask(
                name="Weekly Dependency Check",
                task_type=MaintenanceType.DEPENDENCY_UPDATE,
                command=["pip", "list", "--outdated", "--format=json"],
                schedule_interval="weekly",
            ),
        ]

    def schedule_tasks(self) -> None:
        """Schedule all maintenance tasks."""
        for task in self.tasks:
            if not task.enabled:
                continue

            if task.schedule_interval == "hourly":
                schedule.every().hour.do(self._execute_task, task)
            elif task.schedule_interval == "daily":
                schedule.every().day.at("02:00").do(self._execute_task, task)
            elif task.schedule_interval == "weekly":
                schedule.every().week.do(self._execute_task, task)

        self._log(
            f"Maintenance scheduler initialized with {len([t for t in self.tasks if t.enabled])} tasks"
        )

    def _execute_task(self, task: MaintenanceTask) -> MaintenanceResult:
        """Execute a single maintenance task."""
        start_time = datetime.now()
        self._log(f"Starting maintenance task: {task.name}")

        try:
            result = subprocess.run(
                task.command,
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=300,  # 5 minute timeout
            )

            end_time = datetime.now()
            success = result.returncode == 0

            maintenance_result = MaintenanceResult(
                task_name=task.name,
                success=success,
                start_time=start_time,
                end_time=end_time,
                output=result.stdout,
                error_output=result.stderr,
                exit_code=result.returncode,
            )

            # Update task statistics
            task.last_run = start_time
            if success:
                task.success_count += 1
                self._log(f"Completed maintenance task: {task.name} (SUCCESS)")
            else:
                task.failure_count += 1
                self._log(
                    f"Completed maintenance task: {task.name} (FAILED - exit code {result.returncode})"
                )
                self._log(f"Error output: {result.stderr[:500]}")

            # Save result
            self._save_maintenance_result(maintenance_result)

            return maintenance_result

        except subprocess.TimeoutExpired:
            end_time = datetime.now()
            task.failure_count += 1
            self._log(f"Maintenance task timed out: {task.name}")

            return MaintenanceResult(
                task_name=task.name,
                success=False,
                start_time=start_time,
                end_time=end_time,
                output="",
                error_output="Task timed out after 5 minutes",
                exit_code=-1,
            )

        except Exception as e:
            end_time = datetime.now()
            task.failure_count += 1
            self._log(f"Maintenance task failed with exception: {task.name} - {str(e)}")

            return MaintenanceResult(
                task_name=task.name,
                success=False,
                start_time=start_time,
                end_time=end_time,
                output="",
                error_output=str(e),
                exit_code=-2,
            )

    def run_maintenance_cycle(self) -> None:
        """Run the maintenance scheduler."""
        self._log("Starting maintenance scheduler")

        while True:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except KeyboardInterrupt:
                self._log("Maintenance scheduler stopped by user")
                break
            except Exception as e:
                self._log(f"Maintenance scheduler error: {str(e)}")
                time.sleep(60)  # Continue after error

    def run_all_tasks_once(self) -> list[MaintenanceResult]:
        """Run all maintenance tasks once (for testing/manual execution)."""
        results = []

        for task in self.tasks:
            if task.enabled:
                result = self._execute_task(task)
                results.append(result)

        return results

    def generate_maintenance_report(self) -> dict[str, Any]:
        """Generate maintenance status report."""
        total_tasks = len(self.tasks)
        enabled_tasks = len([t for t in self.tasks if t.enabled])

        # Calculate success rates
        task_stats = []
        for task in self.tasks:
            total_runs = task.success_count + task.failure_count
            success_rate = task.success_count / total_runs if total_runs > 0 else 1.0

            task_stats.append(
                {
                    "name": task.name,
                    "type": task.task_type.value,
                    "enabled": task.enabled,
                    "schedule": task.schedule_interval,
                    "last_run": task.last_run.isoformat() if task.last_run else None,
                    "success_count": task.success_count,
                    "failure_count": task.failure_count,
                    "success_rate": success_rate,
                    "status": (
                        "healthy"
                        if success_rate >= 0.8
                        else "degraded" if success_rate >= 0.5 else "failing"
                    ),
                }
            )

        # Load recent results
        recent_results = self._load_recent_results(limit=50)

        return {
            "summary": {
                "total_tasks": total_tasks,
                "enabled_tasks": enabled_tasks,
                "disabled_tasks": total_tasks - enabled_tasks,
                "report_timestamp": datetime.now().isoformat(),
            },
            "task_statistics": task_stats,
            "recent_results": recent_results,
            "health_status": self._calculate_overall_health(task_stats),
        }

    def _calculate_overall_health(self, task_stats: list[dict]) -> str:
        """Calculate overall maintenance health."""
        enabled_tasks = [t for t in task_stats if t["enabled"]]
        if not enabled_tasks:
            return "unknown"

        healthy_tasks = len([t for t in enabled_tasks if t["status"] == "healthy"])
        degraded_tasks = len([t for t in enabled_tasks if t["status"] == "degraded"])
        failing_tasks = len([t for t in enabled_tasks if t["status"] == "failing"])

        if failing_tasks > 0:
            return "critical"
        elif degraded_tasks > len(enabled_tasks) * 0.3:
            return "degraded"
        elif healthy_tasks >= len(enabled_tasks) * 0.8:
            return "healthy"
        else:
            return "degraded"

    def _save_maintenance_result(self, result: MaintenanceResult) -> None:
        """Save maintenance result to history."""
        results_file = self.project_root / "docs" / "metrics" / "maintenance-results.json"

        # Load existing results
        results = []
        if results_file.exists():
            try:
                with open(results_file) as f:
                    results = json.load(f)
            except Exception:
                results = []

        # Add new result
        results.append(
            {
                "task_name": result.task_name,
                "success": result.success,
                "start_time": result.start_time.isoformat(),
                "end_time": result.end_time.isoformat(),
                "duration_seconds": (result.end_time - result.start_time).total_seconds(),
                "exit_code": result.exit_code,
                "output_length": len(result.output),
                "error_output_length": len(result.error_output),
                "has_error": bool(result.error_output),
            }
        )

        # Keep only last 1000 results
        results = results[-1000:]

        # Save updated results
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2)

    def _load_recent_results(self, limit: int = 50) -> list[dict]:
        """Load recent maintenance results."""
        results_file = self.project_root / "docs" / "metrics" / "maintenance-results.json"

        if not results_file.exists():
            return []

        try:
            with open(results_file) as f:
                results = json.load(f)
            return results[-limit:]
        except Exception:
            return []

    def _log(self, message: str) -> None:
        """Log maintenance message."""
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] {message}\n"

        # Append to log file
        with open(self.maintenance_log, "a") as f:
            f.write(log_entry)

        # Also print to console
        print(log_entry.strip())


def main():
    """Main entry point for maintenance scheduler."""
    import argparse

    parser = argparse.ArgumentParser(description="Automated maintenance scheduler")
    parser.add_argument("--run-once", action="store_true", help="Run all tasks once and exit")
    parser.add_argument("--schedule", action="store_true", help="Start scheduled maintenance")
    parser.add_argument("--report", action="store_true", help="Generate maintenance report")
    parser.add_argument("--status", action="store_true", help="Show maintenance status")

    args = parser.parse_args()

    scheduler = MaintenanceScheduler()

    if args.run_once:
        print("Running all maintenance tasks once...")
        results = scheduler.run_all_tasks_once()

        successful = sum(1 for r in results if r.success)
        total = len(results)
        print(f"\nMaintenance cycle completed: {successful}/{total} tasks successful")

        if successful < total:
            print("Some tasks failed - check maintenance log for details")
            sys.exit(1)

    elif args.schedule:
        scheduler.schedule_tasks()
        scheduler.run_maintenance_cycle()

    elif args.report or args.status:
        report = scheduler.generate_maintenance_report()

        if args.status:
            print(f"Maintenance Status: {report['health_status'].upper()}")
            print(
                f"Tasks: {report['summary']['enabled_tasks']} enabled, {report['summary']['disabled_tasks']} disabled"
            )

            for task in report["task_statistics"]:
                status_icon = (
                    "✅"
                    if task["status"] == "healthy"
                    else "⚠️" if task["status"] == "degraded" else "❌"
                )
                print(
                    f"  {status_icon} {task['name']} ({task['schedule']}) - {task['success_rate']:.1%} success rate"
                )

        if args.report:
            print(json.dumps(report, indent=2))

    else:
        print("Use --run-once, --schedule, --report, or --status")
        sys.exit(1)


if __name__ == "__main__":
    main()
