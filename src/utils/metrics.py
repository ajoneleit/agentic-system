"""Prometheus metrics collection for the Agentic Coding System.

This module provides comprehensive metrics collection for monitoring:
- Task execution performance and success rates
- Agent lifecycle and performance metrics
- API usage and error rates
- System resource utilization
- User interaction patterns
"""

import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from enum import Enum
from typing import Any, Optional

import structlog
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    Summary,
    generate_latest,
    start_http_server,
)

logger = structlog.get_logger(__name__)


class MetricType(Enum):
    """Types of metrics we track."""

    COUNTER = "counter"
    HISTOGRAM = "histogram"
    GAUGE = "gauge"
    SUMMARY = "summary"
    INFO = "info"


class AgenticMetrics:
    """Central metrics collection system for the Agentic Coding System."""

    def __init__(self, registry: Optional[CollectorRegistry] = None):
        """Initialize metrics system.

        Args:
            registry: Custom prometheus registry, uses default if None

        """
        self.registry = registry or CollectorRegistry()
        self._metrics: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._init_metrics()

        logger.info("Metrics system initialized", registry_type=type(self.registry).__name__)

    def _init_metrics(self) -> None:
        """Initialize all metrics."""
        # Task Execution Metrics
        self.task_total = Counter(
            "agentic_tasks_total",
            "Total number of tasks executed",
            ["status", "agent_role", "task_type"],
            registry=self.registry,
        )

        self.task_duration = Histogram(
            "agentic_task_duration_seconds",
            "Time spent executing tasks",
            ["agent_role", "task_type"],
            buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 300.0],
            registry=self.registry,
        )

        self.task_queue_size = Gauge(
            "agentic_task_queue_size",
            "Number of tasks in queue",
            ["priority"],
            registry=self.registry,
        )

        # Agent Performance Metrics
        self.agent_spawned = Counter(
            "agentic_agents_spawned_total",
            "Total number of agents spawned",
            ["agent_role"],
            registry=self.registry,
        )

        self.agent_active = Gauge(
            "agentic_agents_active",
            "Number of currently active agents",
            ["agent_role"],
            registry=self.registry,
        )

        self.agent_memory_usage = Gauge(
            "agentic_agent_memory_bytes",
            "Memory usage per agent",
            ["agent_id", "agent_role"],
            registry=self.registry,
        )

        # API Usage Metrics
        self.api_requests = Counter(
            "agentic_api_requests_total",
            "Total API requests made",
            ["service", "endpoint", "status"],
            registry=self.registry,
        )

        self.api_duration = Histogram(
            "agentic_api_request_duration_seconds",
            "API request duration",
            ["service", "endpoint"],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
            registry=self.registry,
        )

        self.api_rate_limits = Counter(
            "agentic_api_rate_limits_total",
            "Number of rate limit hits",
            ["service"],
            registry=self.registry,
        )

        # Verification System Metrics
        self.verification_attempts = Counter(
            "agentic_verification_attempts_total",
            "Total verification attempts",
            ["verification_type", "result"],
            registry=self.registry,
        )

        self.verification_duration = Histogram(
            "agentic_verification_duration_seconds",
            "Time spent on verification",
            ["verification_type"],
            buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
            registry=self.registry,
        )

        # Artifact Management Metrics
        self.artifacts_created = Counter(
            "agentic_artifacts_created_total",
            "Total artifacts created",
            ["artifact_type"],
            registry=self.registry,
        )

        self.artifacts_stored = Gauge(
            "agentic_artifacts_stored",
            "Number of artifacts currently stored",
            ["artifact_type"],
            registry=self.registry,
        )

        self.artifact_size = Summary(
            "agentic_artifact_size_bytes",
            "Size of artifacts in bytes",
            ["artifact_type"],
            registry=self.registry,
        )

        # System Resource Metrics
        self.system_cpu_usage = Gauge(
            "agentic_system_cpu_usage_percent",
            "System CPU usage percentage",
            registry=self.registry,
        )

        self.system_memory_usage = Gauge(
            "agentic_system_memory_usage_bytes",
            "System memory usage in bytes",
            registry=self.registry,
        )

        self.workspace_files = Gauge(
            "agentic_workspace_files_total",
            "Total files in workspace",
            ["file_type"],
            registry=self.registry,
        )

        # Error Tracking Metrics
        self.errors_total = Counter(
            "agentic_errors_total",
            "Total errors encountered",
            ["error_type", "component"],
            registry=self.registry,
        )

        self.recovery_attempts = Counter(
            "agentic_recovery_attempts_total",
            "Total recovery attempts",
            ["error_type", "strategy", "result"],
            registry=self.registry,
        )

        # User Interaction Metrics
        self.user_requests = Counter(
            "agentic_user_requests_total",
            "Total user requests",
            ["request_type"],
            registry=self.registry,
        )

        self.session_duration = Summary(
            "agentic_session_duration_seconds", "Duration of user sessions", registry=self.registry
        )

        # MCP Integration Metrics
        self.mcp_events_total = Counter(
            "agentic_mcp_events_total",
            "Total MCP events by type and severity",
            ["event_type", "severity", "source", "server"],
            registry=self.registry,
        )

        self.mcp_tool_calls_total = Counter(
            "agentic_mcp_tool_calls_total",
            "Total MCP tool calls by tool and status",
            ["tool", "server", "status"],
            registry=self.registry,
        )

        self.mcp_operation_duration = Histogram(
            "agentic_mcp_operation_duration_seconds",
            "Duration of MCP operations",
            ["operation", "server"],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
            registry=self.registry,
        )

        self.mcp_server_status = Gauge(
            "agentic_mcp_server_status",
            "Status of MCP servers (1=running, 0=stopped)",
            ["server", "status"],
            registry=self.registry,
        )

        self.mcp_connection_count = Gauge(
            "agentic_mcp_connections_active",
            "Number of active MCP connections",
            ["server"],
            registry=self.registry,
        )

        # System Info
        self.system_info = Info(
            "agentic_system_info", "Static system information", registry=self.registry
        )

    def record_task_execution(
        self, status: str, agent_role: str, task_type: str, duration: float
    ) -> None:
        """Record task execution metrics.

        Args:
            status: Task execution status (success, failure, timeout)
            agent_role: Role of the executing agent
            task_type: Type of task executed
            duration: Execution duration in seconds

        """
        self.task_total.labels(status=status, agent_role=agent_role, task_type=task_type).inc()

        self.task_duration.labels(agent_role=agent_role, task_type=task_type).observe(duration)

        logger.debug(
            "Task execution recorded",
            status=status,
            agent_role=agent_role,
            task_type=task_type,
            duration=duration,
        )

    def record_agent_spawn(self, agent_role: str) -> None:
        """Record agent spawning.

        Args:
            agent_role: Role of the spawned agent

        """
        self.agent_spawned.labels(agent_role=agent_role).inc()
        self.agent_active.labels(agent_role=agent_role).inc()

        logger.debug("Agent spawn recorded", agent_role=agent_role)

    def record_agent_shutdown(self, agent_role: str) -> None:
        """Record agent shutdown.

        Args:
            agent_role: Role of the shutdown agent

        """
        self.agent_active.labels(agent_role=agent_role).dec()
        logger.debug("Agent shutdown recorded", agent_role=agent_role)

    def record_api_request(self, service: str, endpoint: str, status: str, duration: float) -> None:
        """Record API request metrics.

        Args:
            service: API service name (claude, openai, etc.)
            endpoint: API endpoint called
            status: Request status (success, error, timeout)
            duration: Request duration in seconds

        """
        self.api_requests.labels(service=service, endpoint=endpoint, status=status).inc()

        self.api_duration.labels(service=service, endpoint=endpoint).observe(duration)

        logger.debug(
            "API request recorded",
            service=service,
            endpoint=endpoint,
            status=status,
            duration=duration,
        )

    def record_rate_limit(self, service: str) -> None:
        """Record API rate limit hit.

        Args:
            service: API service that hit rate limit

        """
        self.api_rate_limits.labels(service=service).inc()
        logger.warning("API rate limit hit", service=service)

    def record_verification(self, verification_type: str, result: str, duration: float) -> None:
        """Record verification attempt.

        Args:
            verification_type: Type of verification (compilation, testing, etc.)
            result: Verification result (success, failure)
            duration: Verification duration in seconds

        """
        self.verification_attempts.labels(verification_type=verification_type, result=result).inc()

        self.verification_duration.labels(verification_type=verification_type).observe(duration)

        logger.debug(
            "Verification recorded",
            verification_type=verification_type,
            result=result,
            duration=duration,
        )

    def record_artifact_creation(self, artifact_type: str, size_bytes: int) -> None:
        """Record artifact creation.

        Args:
            artifact_type: Type of artifact created
            size_bytes: Size of the artifact in bytes

        """
        self.artifacts_created.labels(artifact_type=artifact_type).inc()
        self.artifacts_stored.labels(artifact_type=artifact_type).inc()
        self.artifact_size.labels(artifact_type=artifact_type).observe(size_bytes)

        logger.debug(
            "Artifact creation recorded", artifact_type=artifact_type, size_bytes=size_bytes
        )

    def record_error(self, error_type: str, component: str) -> None:
        """Record error occurrence.

        Args:
            error_type: Type of error
            component: Component where error occurred

        """
        self.errors_total.labels(error_type=error_type, component=component).inc()

        logger.error("Error recorded", error_type=error_type, component=component)

    def record_recovery_attempt(self, error_type: str, strategy: str, result: str) -> None:
        """Record error recovery attempt.

        Args:
            error_type: Type of error being recovered from
            strategy: Recovery strategy used
            result: Recovery attempt result (success, failure)

        """
        self.recovery_attempts.labels(error_type=error_type, strategy=strategy, result=result).inc()

        logger.debug(
            "Recovery attempt recorded", error_type=error_type, strategy=strategy, result=result
        )

    def update_system_metrics(self, cpu_percent: float, memory_bytes: int) -> None:
        """Update system resource metrics.

        Args:
            cpu_percent: CPU usage percentage
            memory_bytes: Memory usage in bytes

        """
        self.system_cpu_usage.set(cpu_percent)
        self.system_memory_usage.set(memory_bytes)

    def update_workspace_metrics(self, file_counts: dict[str, int]) -> None:
        """Update workspace file metrics.

        Args:
            file_counts: Dictionary mapping file types to counts

        """
        for file_type, count in file_counts.items():
            self.workspace_files.labels(file_type=file_type).set(count)

    def set_system_info(self, info: dict[str, str]) -> None:
        """Set static system information.

        Args:
            info: Dictionary of system information

        """
        self.system_info.info(info)
        logger.info("System info updated", **info)

    @contextmanager
    def timer(
        self, metric_name: str, labels: Optional[dict[str, str]] = None
    ) -> Generator[None, None, None]:
        """Context manager for timing operations.

        Args:
            metric_name: Name of the metric to time
            labels: Optional labels for the metric

        Yields:
            None

        """
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time

            # Record to appropriate metric based on name
            if metric_name == "task_duration" and labels:
                self.task_duration.labels(**labels).observe(duration)
            elif metric_name == "api_duration" and labels:
                self.api_duration.labels(**labels).observe(duration)
            elif metric_name == "verification_duration" and labels:
                self.verification_duration.labels(**labels).observe(duration)

    def get_metrics_data(self) -> str:
        """Get current metrics in Prometheus format.

        Returns:
            Metrics data in Prometheus exposition format

        """
        return generate_latest(self.registry)

    def start_metrics_server(self, port: int = 8000) -> None:
        """Start HTTP server for metrics exposition.

        Args:
            port: Port to serve metrics on

        """
        start_http_server(port, registry=self.registry)
        logger.info("Metrics server started", port=port)


# Global metrics instance
_metrics_instance: Optional[AgenticMetrics] = None
_metrics_lock = threading.Lock()


def get_metrics() -> AgenticMetrics:
    """Get the global metrics instance.

    Returns:
        Global AgenticMetrics instance

    """
    global _metrics_instance

    if _metrics_instance is None:
        with _metrics_lock:
            if _metrics_instance is None:
                _metrics_instance = AgenticMetrics()

    return _metrics_instance


def init_metrics(registry: Optional[CollectorRegistry] = None) -> AgenticMetrics:
    """Initialize the global metrics system.

    Args:
        registry: Custom prometheus registry

    Returns:
        Initialized AgenticMetrics instance

    """
    global _metrics_instance

    with _metrics_lock:
        _metrics_instance = AgenticMetrics(registry)

    return _metrics_instance


# Convenience functions for common metrics
def record_task_success(agent_role: str, task_type: str, duration: float) -> None:
    """Record successful task execution."""
    get_metrics().record_task_execution("success", agent_role, task_type, duration)


def record_task_failure(agent_role: str, task_type: str, duration: float) -> None:
    """Record failed task execution."""
    get_metrics().record_task_execution("failure", agent_role, task_type, duration)


def record_api_success(service: str, endpoint: str, duration: float) -> None:
    """Record successful API request."""
    get_metrics().record_api_request(service, endpoint, "success", duration)


def record_api_error(service: str, endpoint: str, duration: float) -> None:
    """Record failed API request."""
    get_metrics().record_api_request(service, endpoint, "error", duration)


def record_verification_success(verification_type: str, duration: float) -> None:
    """Record successful verification."""
    get_metrics().record_verification(verification_type, "success", duration)


def record_verification_failure(verification_type: str, duration: float) -> None:
    """Record failed verification."""
    get_metrics().record_verification(verification_type, "failure", duration)
