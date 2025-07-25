"""Observability system initialization for the Agentic Coding System.

This module handles the startup and configuration of the complete observability
stack including structured logging, metrics collection, and performance tracking.
"""

import atexit
import os
import threading
from typing import Optional

import psutil
import structlog
from prometheus_client import start_http_server

from config import get_settings

from .app_logging import setup_logging
from .metrics import get_metrics, init_metrics
from .observability import setup_observability

logger = structlog.get_logger(__name__)


class ObservabilityManager:
    """Manages the complete observability system lifecycle."""

    def __init__(self):
        """Initialize the observability manager."""
        self.settings = get_settings()
        self.metrics_server_thread: Optional[threading.Thread] = None
        self.system_monitor_thread: Optional[threading.Thread] = None
        self.is_running = False
        self._shutdown_event = threading.Event()

    def initialize(self) -> None:
        """Initialize the complete observability system."""
        logger.info("Initializing observability system")

        # Setup structured logging first
        if self.settings.observability.enable_structured_logging:
            setup_logging(
                log_level=self.settings.logging.level,
                log_file=self.settings.logging.file_path,
                use_json=self.settings.logging.format == "json",
            )
            logger.info("Structured logging initialized")

        # Initialize metrics collection
        if self.settings.observability.enable_metrics:
            metrics = init_metrics()

            # Set system information
            metrics.set_system_info(
                {
                    "application": self.settings.project_name,
                    "version": self.settings.version,
                    "environment": self.settings.environment.value,
                    "python_version": f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
                    "process_id": str(os.getpid()),
                }
            )

            logger.info("Metrics collection initialized")

        # Setup enhanced observability (logging + metrics integration)
        if (
            self.settings.observability.enable_structured_logging
            and self.settings.observability.enable_metrics
        ):
            setup_observability()
            logger.info("Enhanced observability integration enabled")

        # Start metrics HTTP server
        if self.settings.observability.enable_metrics:
            self._start_metrics_server()

        # Start system monitoring
        if self.settings.observability.enable_system_metrics:
            self._start_system_monitoring()

        # Register shutdown handler
        atexit.register(self.shutdown)

        self.is_running = True
        logger.info(
            "Observability system fully initialized",
            metrics_enabled=self.settings.observability.enable_metrics,
            metrics_port=self.settings.observability.metrics_port,
            structured_logging=self.settings.observability.enable_structured_logging,
            performance_tracking=self.settings.observability.enable_performance_tracking,
            system_monitoring=self.settings.observability.enable_system_metrics,
        )

    def _start_metrics_server(self) -> None:
        """Start the Prometheus metrics HTTP server."""
        try:
            start_http_server(
                self.settings.observability.metrics_port, registry=get_metrics().registry
            )
            logger.info(
                "Metrics HTTP server started",
                port=self.settings.observability.metrics_port,
                endpoint=f"http://localhost:{self.settings.observability.metrics_port}/metrics",
            )
        except Exception as e:
            logger.error(
                "Failed to start metrics server",
                error=str(e),
                port=self.settings.observability.metrics_port,
            )

    def _start_system_monitoring(self) -> None:
        """Start background system monitoring."""

        def monitor_system():
            """Monitor system resources periodically."""
            logger.debug("Starting system resource monitoring")

            while not self._shutdown_event.is_set():
                try:
                    # Get system metrics
                    cpu_percent = psutil.cpu_percent(interval=1)
                    memory_info = psutil.virtual_memory()
                    disk_info = psutil.disk_usage("/")

                    # Update metrics
                    metrics = get_metrics()
                    metrics.update_system_metrics(cpu_percent, memory_info.used)

                    # Log system status periodically
                    logger.debug(
                        "System metrics updated",
                        system={
                            "cpu": cpu_percent,
                            "memory": memory_info.used,
                            "memory_percent": memory_info.percent,
                            "disk_used": disk_info.used,
                            "disk_percent": (disk_info.used / disk_info.total) * 100,
                        },
                    )

                    # Wait for next collection interval
                    self._shutdown_event.wait(
                        self.settings.observability.metrics_collection_interval
                    )

                except Exception as e:
                    logger.warning("Error collecting system metrics", error=str(e))
                    self._shutdown_event.wait(
                        self.settings.observability.metrics_collection_interval
                    )

        self.system_monitor_thread = threading.Thread(
            target=monitor_system, name="SystemMonitor", daemon=True
        )
        self.system_monitor_thread.start()
        logger.info("System monitoring started")

    def get_health_status(self) -> dict:
        """Get the health status of the observability system.

        Returns:
            Dictionary containing health information

        """
        status = {
            "observability_running": self.is_running,
            "metrics_enabled": self.settings.observability.enable_metrics,
            "structured_logging": self.settings.observability.enable_structured_logging,
            "performance_tracking": self.settings.observability.enable_performance_tracking,
            "system_monitoring": self.settings.observability.enable_system_metrics,
        }

        if self.settings.observability.enable_metrics:
            status["metrics_port"] = self.settings.observability.metrics_port
            status["metrics_endpoint"] = (
                f"http://localhost:{self.settings.observability.metrics_port}/metrics"
            )

        if self.system_monitor_thread:
            status["system_monitor_running"] = self.system_monitor_thread.is_alive()

        return status

    def shutdown(self) -> None:
        """Shutdown the observability system."""
        if not self.is_running:
            return

        logger.info("Shutting down observability system")

        # Signal shutdown to all threads
        self._shutdown_event.set()

        # Wait for system monitor thread to finish
        if self.system_monitor_thread and self.system_monitor_thread.is_alive():
            self.system_monitor_thread.join(timeout=5)
            if self.system_monitor_thread.is_alive():
                logger.warning("System monitor thread did not shutdown cleanly")

        self.is_running = False
        logger.info("Observability system shutdown complete")


# Global observability manager instance
_observability_manager: Optional[ObservabilityManager] = None
_manager_lock = threading.Lock()


def get_observability_manager() -> ObservabilityManager:
    """Get the global observability manager instance.

    Returns:
        Global ObservabilityManager instance

    """
    global _observability_manager

    if _observability_manager is None:
        with _manager_lock:
            if _observability_manager is None:
                _observability_manager = ObservabilityManager()

    return _observability_manager


def initialize_observability() -> ObservabilityManager:
    """Initialize the complete observability system.

    Returns:
        Initialized ObservabilityManager instance

    """
    manager = get_observability_manager()
    manager.initialize()
    return manager


def get_health_status() -> dict:
    """Get observability system health status.

    Returns:
        Health status dictionary

    """
    if _observability_manager is None:
        return {"observability_running": False, "status": "not_initialized"}

    return _observability_manager.get_health_status()


def shutdown_observability() -> None:
    """Shutdown the observability system."""
    if _observability_manager is not None:
        _observability_manager.shutdown()
