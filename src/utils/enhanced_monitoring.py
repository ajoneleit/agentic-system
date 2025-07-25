"""Enhanced monitoring system for comprehensive agent status detection and logging.

This module provides detailed agent activity tracking, progress monitoring,
and structured logging for identifying stuck agents and system bottlenecks.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from structlog import get_logger

from src.core.coordinator import AgentMetrics, AgentStatus
from src.utils.metrics import get_metrics

logger = get_logger(__name__)


class LogLevel(Enum):
    """Enhanced log levels for agent monitoring."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AgentActivityLog:
    """Structured log entry for agent activity."""

    timestamp: datetime
    agent_id: str
    event_type: str
    level: LogLevel
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "event_type": self.event_type,
            "level": self.level.value,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class SystemProgressReport:
    """Comprehensive system progress report."""

    timestamp: datetime
    total_agents: int
    active_agents: int
    stuck_agents: int
    completed_tasks: int
    failed_tasks: int
    pending_tasks: int
    system_health_score: float
    bottlenecks: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_agents": self.total_agents,
            "active_agents": self.active_agents,
            "stuck_agents": self.stuck_agents,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "pending_tasks": self.pending_tasks,
            "system_health_score": self.system_health_score,
            "bottlenecks": self.bottlenecks,
            "recommendations": self.recommendations,
        }


class EnhancedMonitoringSystem:
    """Comprehensive monitoring system for agent status and progress tracking."""

    def __init__(self, max_log_entries: int = 10000):
        """Initialize the enhanced monitoring system.

        Args:
            max_log_entries: Maximum number of log entries to keep in memory

        """
        self.max_log_entries = max_log_entries
        self.activity_logs: list[AgentActivityLog] = []
        self.progress_reports: list[SystemProgressReport] = []
        self.metrics = get_metrics()
        self._log_lock = asyncio.Lock()

        # Monitoring thresholds
        self.stuck_threshold_seconds = 300  # 5 minutes
        self.heartbeat_timeout_seconds = 60  # 1 minute
        self.health_check_interval = 10  # seconds

        # Performance tracking
        self.start_time = datetime.utcnow()
        self.last_health_check = datetime.utcnow()

        logger.info("Enhanced monitoring system initialized")

    async def log_agent_activity(
        self, agent_id: UUID, event_type: str, level: LogLevel, message: str, **details
    ) -> None:
        """Log agent activity with structured data.

        Args:
            agent_id: Agent identifier
            event_type: Type of event (task_start, progress_update, etc.)
            level: Log level
            message: Human-readable message
            **details: Additional structured data

        """
        async with self._log_lock:
            log_entry = AgentActivityLog(
                timestamp=datetime.utcnow(),
                agent_id=str(agent_id),
                event_type=event_type,
                level=level,
                message=message,
                details=details,
            )

            self.activity_logs.append(log_entry)

            # Rotate logs if needed
            if len(self.activity_logs) > self.max_log_entries:
                self.activity_logs = self.activity_logs[-self.max_log_entries :]

            # Emit structured log
            log_data = log_entry.to_dict()
            getattr(logger, level.value)(f"Agent Activity: {message}", **log_data)

            # Update metrics
            if event_type == "task_completed":
                status = details.get("status", "unknown")
                agent_role = details.get("agent_role", "unknown")
                task_type = details.get("task_type", "unknown")
                duration = details.get("duration", 0)

                self.metrics.record_task_execution(status, agent_role, task_type, duration)

            elif event_type == "stuck_detected":
                self.metrics.record_error("stuck_agent", f"agent_{agent_id}")

            elif event_type == "recovery_attempted":
                strategy = details.get("strategy", "unknown")
                result = details.get("result", "unknown")
                self.metrics.record_recovery_attempt("stuck_agent", strategy, result)

    async def log_progress_update(
        self, agent_id: UUID, operation: str, progress_percentage: float, **details
    ) -> None:
        """Log agent progress update.

        Args:
            agent_id: Agent identifier
            operation: Current operation name
            progress_percentage: Progress percentage (0-100)
            **details: Additional progress details

        """
        await self.log_agent_activity(
            agent_id=agent_id,
            event_type="progress_update",
            level=LogLevel.INFO,
            message=f"Agent progress: {operation} ({progress_percentage:.1f}%)",
            operation=operation,
            progress_percentage=progress_percentage,
            **details,
        )

    async def log_stuck_agent(
        self,
        agent_id: UUID,
        current_operation: str,
        operation_duration: float,
        last_heartbeat_age: float,
        **details,
    ) -> None:
        """Log stuck agent detection.

        Args:
            agent_id: Agent identifier
            current_operation: Current operation that appears stuck
            operation_duration: How long the operation has been running
            last_heartbeat_age: Age of last heartbeat in seconds
            **details: Additional stuck detection details

        """
        await self.log_agent_activity(
            agent_id=agent_id,
            event_type="stuck_detected",
            level=LogLevel.WARNING,
            message=f"Agent stuck in operation: {current_operation}",
            current_operation=current_operation,
            operation_duration=operation_duration,
            last_heartbeat_age=last_heartbeat_age,
            **details,
        )

    async def log_recovery_attempt(
        self, agent_id: UUID, strategy: str, attempt_number: int, **details
    ) -> None:
        """Log recovery attempt.

        Args:
            agent_id: Agent identifier
            strategy: Recovery strategy used
            attempt_number: Recovery attempt number
            **details: Additional recovery details

        """
        await self.log_agent_activity(
            agent_id=agent_id,
            event_type="recovery_attempted",
            level=LogLevel.WARNING,
            message=f"Recovery attempt #{attempt_number}: {strategy}",
            strategy=strategy,
            attempt_number=attempt_number,
            **details,
        )

    async def generate_progress_report(
        self,
        agent_metrics: dict[UUID, AgentMetrics],
        agent_status: dict[UUID, AgentStatus],
        task_counts: dict[str, int],
    ) -> SystemProgressReport:
        """Generate comprehensive system progress report.

        Args:
            agent_metrics: Current agent metrics
            agent_status: Current agent status
            task_counts: Task count information

        Returns:
            SystemProgressReport with current system state

        """
        now = datetime.utcnow()

        # Calculate status counts
        status_counts = {}
        for status in agent_status.values():
            status_counts[status.value] = status_counts.get(status.value, 0) + 1

        total_agents = len(agent_metrics)
        active_agents = status_counts.get("working", 0)
        stuck_agents = status_counts.get("stuck", 0)

        # Calculate system health score
        health_score = self._calculate_health_score(agent_metrics, agent_status, task_counts)

        # Identify bottlenecks
        bottlenecks = self._identify_bottlenecks(agent_metrics, agent_status, task_counts)

        # Generate recommendations
        recommendations = self._generate_recommendations(agent_metrics, agent_status, bottlenecks)

        report = SystemProgressReport(
            timestamp=now,
            total_agents=total_agents,
            active_agents=active_agents,
            stuck_agents=stuck_agents,
            completed_tasks=task_counts.get("completed", 0),
            failed_tasks=task_counts.get("failed", 0),
            pending_tasks=task_counts.get("pending", 0),
            system_health_score=health_score,
            bottlenecks=bottlenecks,
            recommendations=recommendations,
        )

        # Store report
        self.progress_reports.append(report)

        # Rotate reports if needed
        if len(self.progress_reports) > 1000:
            self.progress_reports = self.progress_reports[-1000:]

        # Log report
        logger.info("System progress report generated", **report.to_dict())

        return report

    def _calculate_health_score(
        self,
        agent_metrics: dict[UUID, AgentMetrics],
        agent_status: dict[UUID, AgentStatus],
        task_counts: dict[str, int],
    ) -> float:
        """Calculate system health score (0-100).

        Args:
            agent_metrics: Current agent metrics
            agent_status: Current agent status
            task_counts: Task count information

        Returns:
            Health score between 0 and 100

        """
        if not agent_metrics:
            return 0.0

        # Base score starts at 100
        health_score = 100.0

        # Penalize stuck agents
        stuck_count = sum(1 for status in agent_status.values() if status == AgentStatus.STUCK)
        stuck_penalty = (stuck_count / len(agent_metrics)) * 30
        health_score -= stuck_penalty

        # Penalize failed agents
        failed_count = sum(1 for status in agent_status.values() if status == AgentStatus.ERROR)
        failed_penalty = (failed_count / len(agent_metrics)) * 20
        health_score -= failed_penalty

        # Penalize low success rates
        avg_success_rate = sum(m.success_rate for m in agent_metrics.values()) / len(agent_metrics)
        success_penalty = (1.0 - avg_success_rate) * 25
        health_score -= success_penalty

        # Penalize high recovery attempt rates
        avg_recovery_rate = sum(m.recovery_attempts for m in agent_metrics.values()) / len(
            agent_metrics
        )
        recovery_penalty = min(avg_recovery_rate * 5, 15)  # Cap at 15 points
        health_score -= recovery_penalty

        return max(0.0, min(100.0, health_score))

    def _identify_bottlenecks(
        self,
        agent_metrics: dict[UUID, AgentMetrics],
        agent_status: dict[UUID, AgentStatus],
        task_counts: dict[str, int],
    ) -> list[str]:
        """Identify system bottlenecks.

        Args:
            agent_metrics: Current agent metrics
            agent_status: Current agent status
            task_counts: Task count information

        Returns:
            List of identified bottlenecks

        """
        bottlenecks = []

        # Check for stuck agents
        stuck_agents = [
            agent_id for agent_id, status in agent_status.items() if status == AgentStatus.STUCK
        ]
        if stuck_agents:
            bottlenecks.append(f"Stuck agents detected: {len(stuck_agents)} agents")

        # Check for high failure rates
        failed_agents = [
            agent_id for agent_id, metrics in agent_metrics.items() if metrics.success_rate < 0.8
        ]
        if failed_agents:
            bottlenecks.append(f"High failure rate agents: {len(failed_agents)} agents")

        # Check for long-running operations
        long_running = [
            agent_id
            for agent_id, metrics in agent_metrics.items()
            if metrics.get_operation_duration() > 600  # 10 minutes
        ]
        if long_running:
            bottlenecks.append(f"Long-running operations: {len(long_running)} agents")

        # Check for high recovery attempt rates
        high_recovery = [
            agent_id for agent_id, metrics in agent_metrics.items() if metrics.recovery_attempts > 5
        ]
        if high_recovery:
            bottlenecks.append(f"High recovery attempts: {len(high_recovery)} agents")

        return bottlenecks

    def _generate_recommendations(
        self,
        agent_metrics: dict[UUID, AgentMetrics],
        agent_status: dict[UUID, AgentStatus],
        bottlenecks: list[str],
    ) -> list[str]:
        """Generate recommendations for system improvement.

        Args:
            agent_metrics: Current agent metrics
            agent_status: Current agent status
            bottlenecks: Identified bottlenecks

        Returns:
            List of recommendations

        """
        recommendations = []

        # Recommendations based on bottlenecks
        if any("stuck" in b.lower() for b in bottlenecks):
            recommendations.append("Consider reducing task timeouts or improving stuck detection")

        if any("failure" in b.lower() for b in bottlenecks):
            recommendations.append("Investigate common failure patterns and improve error handling")

        if any("long-running" in b.lower() for b in bottlenecks):
            recommendations.append("Break down long-running tasks into smaller sub-tasks")

        if any("recovery" in b.lower() for b in bottlenecks):
            recommendations.append("Improve task design to reduce need for recovery attempts")

        # General recommendations
        avg_success_rate = (
            sum(m.success_rate for m in agent_metrics.values()) / len(agent_metrics)
            if agent_metrics
            else 0
        )
        if avg_success_rate < 0.9:
            recommendations.append("Overall success rate is low, consider system optimization")

        if not recommendations:
            recommendations.append("System is performing well, no immediate action needed")

        return recommendations

    async def get_recent_activity(
        self,
        agent_id: Optional[UUID] = None,
        event_type: Optional[str] = None,
        level: Optional[LogLevel] = None,
        limit: int = 100,
    ) -> list[AgentActivityLog]:
        """Get recent agent activity logs.

        Args:
            agent_id: Filter by agent ID
            event_type: Filter by event type
            level: Filter by log level
            limit: Maximum number of entries to return

        Returns:
            List of filtered activity logs

        """
        async with self._log_lock:
            filtered_logs = self.activity_logs

            if agent_id:
                filtered_logs = [log for log in filtered_logs if log.agent_id == str(agent_id)]

            if event_type:
                filtered_logs = [log for log in filtered_logs if log.event_type == event_type]

            if level:
                filtered_logs = [log for log in filtered_logs if log.level == level]

            # Sort by timestamp (newest first) and limit
            filtered_logs.sort(key=lambda x: x.timestamp, reverse=True)
            return filtered_logs[:limit]

    async def clear_logs(self) -> None:
        """Clear all stored activity logs."""
        async with self._log_lock:
            self.activity_logs.clear()
            logger.info("Activity logs cleared")

    async def get_system_summary(self) -> dict[str, Any]:
        """Get comprehensive system monitoring summary.

        Returns:
            Dictionary with system monitoring summary

        """
        recent_logs = await self.get_recent_activity(limit=1000)

        # Count events by type
        event_counts = {}
        for log in recent_logs:
            event_counts[log.event_type] = event_counts.get(log.event_type, 0) + 1

        # Count events by level
        level_counts = {}
        for log in recent_logs:
            level_counts[log.level.value] = level_counts.get(log.level.value, 0) + 1

        # Get latest progress report
        latest_report = self.progress_reports[-1].to_dict() if self.progress_reports else None

        return {
            "monitoring_start_time": self.start_time.isoformat(),
            "total_log_entries": len(self.activity_logs),
            "recent_event_counts": event_counts,
            "recent_level_counts": level_counts,
            "latest_progress_report": latest_report,
            "system_uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds(),
        }


# Global monitoring instance
_monitoring_system: Optional[EnhancedMonitoringSystem] = None


def get_monitoring_system() -> EnhancedMonitoringSystem:
    """Get the global monitoring system instance."""
    global _monitoring_system
    if _monitoring_system is None:
        _monitoring_system = EnhancedMonitoringSystem()
    return _monitoring_system


async def log_agent_activity(
    agent_id: UUID, event_type: str, level: LogLevel, message: str, **details
) -> None:
    """Convenience function for logging agent activity."""
    monitoring = get_monitoring_system()
    await monitoring.log_agent_activity(agent_id, event_type, level, message, **details)


async def log_progress_update(
    agent_id: UUID, operation: str, progress_percentage: float, **details
) -> None:
    """Convenience function for logging progress updates."""
    monitoring = get_monitoring_system()
    await monitoring.log_progress_update(agent_id, operation, progress_percentage, **details)


async def log_stuck_agent(
    agent_id: UUID,
    current_operation: str,
    operation_duration: float,
    last_heartbeat_age: float,
    **details,
) -> None:
    """Convenience function for logging stuck agents."""
    monitoring = get_monitoring_system()
    await monitoring.log_stuck_agent(
        agent_id, current_operation, operation_duration, last_heartbeat_age, **details
    )


async def log_recovery_attempt(
    agent_id: UUID, strategy: str, attempt_number: int, **details
) -> None:
    """Convenience function for logging recovery attempts."""
    monitoring = get_monitoring_system()
    await monitoring.log_recovery_attempt(agent_id, strategy, attempt_number, **details)
