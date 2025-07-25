"""Observability integration for the Agentic Coding System.

This module provides enhanced observability by combining structured logging
with metrics collection, enabling comprehensive monitoring and debugging.
"""

import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Optional
from uuid import UUID

import structlog

from .metrics import AgenticMetrics, get_metrics

logger = structlog.get_logger(__name__)


class MetricsProcessor:
    """Structlog processor that automatically emits metrics based on log events."""

    def __init__(self, metrics: Optional[AgenticMetrics] = None):
        """Initialize processor.

        Args:
            metrics: Metrics instance to use, defaults to global instance

        """
        self.metrics = metrics or get_metrics()
        self._active_timers: dict[str, float] = {}
        self._lock = threading.Lock()

    def __call__(self, logger: Any, name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        """Process log event and emit relevant metrics.

        Args:
            logger: Logger instance
            name: Logger name
            event_dict: Event dictionary

        Returns:
            Unmodified event dictionary

        """
        try:
            self._process_event(event_dict)
        except Exception as e:
            # Don't break logging if metrics fail
            logger.warning("Failed to process metrics from log", error=str(e))

        return event_dict

    def _process_event(self, event_dict: dict[str, Any]) -> None:
        """Process a single log event for metrics extraction.

        Args:
            event_dict: Log event dictionary

        """
        event = event_dict.get("event", "")
        level = event_dict.get("level", "")

        # Task execution metrics
        if "task" in event_dict:
            self._process_task_event(event_dict, event, level)

        # Agent lifecycle metrics
        if "agent" in event_dict:
            self._process_agent_event(event_dict, event, level)

        # API request metrics
        if "api" in event_dict or "request" in event:
            self._process_api_event(event_dict, event, level)

        # Verification metrics
        if "verification" in event_dict or "verify" in event:
            self._process_verification_event(event_dict, event, level)

        # Error metrics
        if level in ["error", "critical"] or "error" in event_dict:
            self._process_error_event(event_dict, event, level)

        # System metrics
        if "system" in event_dict:
            self._process_system_event(event_dict, event, level)

    def _process_task_event(self, event_dict: dict[str, Any], event: str, level: str) -> None:
        """Process task-related events."""
        task_info = event_dict.get("task", {})

        if "completed" in event or "finished" in event:
            status = "success" if level != "error" else "failure"
            agent_role = task_info.get("agent_role", "unknown")
            task_type = task_info.get("type", "unknown")
            duration = task_info.get("duration", 0)

            self.metrics.record_task_execution(status, agent_role, task_type, duration)

        elif "queue" in event_dict:
            priority = event_dict["queue"].get("priority", "normal")
            size = event_dict["queue"].get("size", 0)
            self.metrics.task_queue_size.labels(priority=priority).set(size)

    def _process_agent_event(self, event_dict: dict[str, Any], event: str, level: str) -> None:
        """Process agent-related events."""
        agent_info = event_dict.get("agent", {})
        agent_role = agent_info.get("role", "unknown")

        if "spawned" in event or "created" in event:
            self.metrics.record_agent_spawn(agent_role)

        elif "shutdown" in event or "terminated" in event:
            self.metrics.record_agent_shutdown(agent_role)

        elif "memory" in agent_info:
            agent_id = agent_info.get("id", "unknown")
            memory_bytes = agent_info["memory"]
            self.metrics.agent_memory_usage.labels(agent_id=agent_id, agent_role=agent_role).set(
                memory_bytes
            )

    def _process_api_event(self, event_dict: dict[str, Any], event: str, level: str) -> None:
        """Process API-related events."""
        api_info = event_dict.get("api", {})
        service = api_info.get("service", "unknown")
        endpoint = api_info.get("endpoint", "unknown")

        if "request" in event:
            status = "success" if level != "error" else "error"
            duration = api_info.get("duration", 0)

            self.metrics.record_api_request(service, endpoint, status, duration)

        elif "rate_limit" in event or "throttled" in event:
            self.metrics.record_rate_limit(service)

    def _process_verification_event(
        self, event_dict: dict[str, Any], event: str, level: str
    ) -> None:
        """Process verification-related events."""
        verification_info = event_dict.get("verification", {})
        verification_type = verification_info.get("type", "unknown")

        if "completed" in event or "finished" in event:
            result = "success" if level != "error" else "failure"
            duration = verification_info.get("duration", 0)

            self.metrics.record_verification(verification_type, result, duration)

    def _process_error_event(self, event_dict: dict[str, Any], event: str, level: str) -> None:
        """Process error-related events."""
        error_info = event_dict.get("error", {})
        error_type = error_info.get("type", event_dict.get("exc_info", {}).get("type", "unknown"))
        component = event_dict.get("component", event_dict.get("name", "unknown"))

        self.metrics.record_error(error_type, component)

        # Recovery attempts
        if "recovery" in event_dict:
            recovery_info = event_dict["recovery"]
            strategy = recovery_info.get("strategy", "unknown")
            result = recovery_info.get("result", "unknown")

            self.metrics.record_recovery_attempt(error_type, strategy, result)

    def _process_system_event(self, event_dict: dict[str, Any], event: str, level: str) -> None:
        """Process system-related events."""
        system_info = event_dict.get("system", {})

        if "cpu" in system_info and "memory" in system_info:
            self.metrics.update_system_metrics(system_info["cpu"], system_info["memory"])

        elif "workspace" in system_info:
            file_counts = system_info["workspace"].get("file_counts", {})
            self.metrics.update_workspace_metrics(file_counts)


class ObservabilityContext:
    """Context manager for tracking operations with both logging and metrics."""

    def __init__(
        self,
        operation_name: str,
        logger: Optional[structlog.BoundLogger] = None,
        metrics: Optional[AgenticMetrics] = None,
        **context_data: Any,
    ):
        """Initialize observability context.

        Args:
            operation_name: Name of the operation being tracked
            logger: Logger to use, defaults to module logger
            metrics: Metrics instance to use, defaults to global instance
            **context_data: Additional context data for logging

        """
        self.operation_name = operation_name
        self.logger = logger or structlog.get_logger()
        self.metrics = metrics or get_metrics()
        self.context_data = context_data
        self.start_time: Optional[float] = None

    def __enter__(self) -> "ObservabilityContext":
        """Enter the context."""
        self.start_time = time.time()

        self.logger.info(
            f"Starting {self.operation_name}", operation=self.operation_name, **self.context_data
        )

        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the context."""
        duration = time.time() - (self.start_time or time.time())

        if exc_type is None:
            # Success
            self.logger.info(
                f"Completed {self.operation_name}",
                operation=self.operation_name,
                duration=duration,
                status="success",
                **self.context_data,
            )
        else:
            # Error
            self.logger.error(
                f"Failed {self.operation_name}",
                operation=self.operation_name,
                duration=duration,
                status="error",
                error_type=exc_type.__name__ if exc_type else "unknown",
                error_message=str(exc_val) if exc_val else "unknown",
                **self.context_data,
            )


class PerformanceTracker:
    """High-level performance tracking for key system operations."""

    def __init__(self, metrics: Optional[AgenticMetrics] = None):
        """Initialize performance tracker.

        Args:
            metrics: Metrics instance to use

        """
        self.metrics = metrics or get_metrics()
        self.logger = structlog.get_logger(__name__)

    @contextmanager
    def track_task_execution(
        self, agent_role: str, task_type: str, task_id: Optional[UUID] = None
    ) -> Generator[None, None, None]:
        """Track task execution performance.

        Args:
            agent_role: Role of the executing agent
            task_type: Type of task being executed
            task_id: Optional task ID for correlation

        """
        start_time = time.time()

        self.logger.info(
            "Task execution started",
            task={
                "id": str(task_id) if task_id else None,
                "agent_role": agent_role,
                "type": task_type,
            },
        )

        try:
            yield
            duration = time.time() - start_time

            self.metrics.record_task_execution("success", agent_role, task_type, duration)

            self.logger.info(
                "Task execution completed",
                task={
                    "id": str(task_id) if task_id else None,
                    "agent_role": agent_role,
                    "type": task_type,
                    "duration": duration,
                },
            )

        except Exception as e:
            duration = time.time() - start_time

            self.metrics.record_task_execution("failure", agent_role, task_type, duration)

            self.logger.error(
                "Task execution failed",
                task={
                    "id": str(task_id) if task_id else None,
                    "agent_role": agent_role,
                    "type": task_type,
                    "duration": duration,
                },
                error_type=e.__class__.__name__,
                error_message=str(e),
            )
            raise

    @contextmanager
    def track_api_request(self, service: str, endpoint: str) -> Generator[None, None, None]:
        """Track API request performance.

        Args:
            service: API service name
            endpoint: API endpoint

        """
        start_time = time.time()

        self.logger.debug("API request started", api={"service": service, "endpoint": endpoint})

        try:
            yield
            duration = time.time() - start_time

            self.metrics.record_api_request(service, endpoint, "success", duration)

            self.logger.debug(
                "API request completed",
                api={"service": service, "endpoint": endpoint, "duration": duration},
            )

        except Exception as e:
            duration = time.time() - start_time

            self.metrics.record_api_request(service, endpoint, "error", duration)

            self.logger.warning(
                "API request failed",
                api={"service": service, "endpoint": endpoint, "duration": duration},
                error_type=e.__class__.__name__,
                error_message=str(e),
            )
            raise

    @contextmanager
    def track_verification(
        self, verification_type: str, artifact_id: Optional[UUID] = None
    ) -> Generator[None, None, None]:
        """Track verification performance.

        Args:
            verification_type: Type of verification
            artifact_id: Optional artifact ID being verified

        """
        start_time = time.time()

        self.logger.info(
            "Verification started",
            verification={
                "type": verification_type,
                "artifact_id": str(artifact_id) if artifact_id else None,
            },
        )

        try:
            yield
            duration = time.time() - start_time

            self.metrics.record_verification(verification_type, "success", duration)

            self.logger.info(
                "Verification completed",
                verification={
                    "type": verification_type,
                    "artifact_id": str(artifact_id) if artifact_id else None,
                    "duration": duration,
                },
            )

        except Exception as e:
            duration = time.time() - start_time

            self.metrics.record_verification(verification_type, "failure", duration)

            self.logger.error(
                "Verification failed",
                verification={
                    "type": verification_type,
                    "artifact_id": str(artifact_id) if artifact_id else None,
                    "duration": duration,
                },
                error_type=e.__class__.__name__,
                error_message=str(e),
            )
            raise


# Global instances
_metrics_processor: Optional[MetricsProcessor] = None
_performance_tracker: Optional[PerformanceTracker] = None


def get_metrics_processor() -> MetricsProcessor:
    """Get the global metrics processor instance."""
    global _metrics_processor
    if _metrics_processor is None:
        _metrics_processor = MetricsProcessor()
    return _metrics_processor


def get_performance_tracker() -> PerformanceTracker:
    """Get the global performance tracker instance."""
    global _performance_tracker
    if _performance_tracker is None:
        _performance_tracker = PerformanceTracker()
    return _performance_tracker


def setup_observability() -> None:
    """Setup observability by adding metrics processor to structlog."""
    # Add metrics processor to structlog configuration
    current_config = structlog.get_config()
    processors = list(current_config.get("processors", []))

    # Add metrics processor early in the chain (but after basic processors)
    metrics_processor = get_metrics_processor()
    if metrics_processor not in processors:
        # Insert after basic structlog processors but before formatters
        insert_index = len(processors) - 1  # Before the formatter
        processors.insert(insert_index, metrics_processor)

    # Reconfigure structlog with metrics processor
    structlog.configure(
        processors=processors,
        context_class=current_config.get("context_class", dict),
        logger_factory=current_config.get("logger_factory", structlog.stdlib.LoggerFactory()),
        cache_logger_on_first_use=current_config.get("cache_logger_on_first_use", True),
    )

    logger.info("Observability setup completed with metrics integration")
