"""MCP State Transition Events for the Agentic Coding System.

This module implements a comprehensive event system for tracking state transitions
in the Model Context Protocol (MCP) integration, enabling detailed monitoring
and debugging of agent interactions with MCP servers.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Callable, Union
from uuid import UUID, uuid4
import threading
from collections import defaultdict

import structlog

from .interfaces import TaskStatus, AgentRole
from ..utils.metrics import get_metrics

logger = structlog.get_logger(__name__)


class MCPEventType(Enum):
    """Types of MCP events."""
    
    # Server lifecycle events
    SERVER_STARTING = "server_starting"
    SERVER_STARTED = "server_started"
    SERVER_STOPPING = "server_stopping"
    SERVER_STOPPED = "server_stopped"
    SERVER_ERROR = "server_error"
    SERVER_CRASHED = "server_crashed"
    
    # Connection events
    CONNECTION_ESTABLISHING = "connection_establishing"
    CONNECTION_ESTABLISHED = "connection_established"
    CONNECTION_LOST = "connection_lost"
    CONNECTION_RESTORED = "connection_restored"
    CONNECTION_CLOSED = "connection_closed"
    
    # Tool execution events
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    TOOL_CALL_FAILED = "tool_call_failed"
    TOOL_CALL_TIMEOUT = "tool_call_timeout"
    TOOL_CALL_CANCELLED = "tool_call_cancelled"
    
    # Resource events
    RESOURCE_ACCESSED = "resource_accessed"
    RESOURCE_CREATED = "resource_created"
    RESOURCE_MODIFIED = "resource_modified"
    RESOURCE_DELETED = "resource_deleted"
    RESOURCE_ACCESS_DENIED = "resource_access_denied"
    
    # Security events
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_DENIED = "permission_denied"
    SECURITY_VIOLATION = "security_violation"
    SANDBOX_BREACH = "sandbox_breach"
    
    # Agent interaction events
    AGENT_TASK_STARTED = "agent_task_started"
    AGENT_TASK_COMPLETED = "agent_task_completed"
    AGENT_TASK_FAILED = "agent_task_failed"
    AGENT_CONTEXT_SWITCH = "agent_context_switch"
    
    # Workspace events
    WORKSPACE_CREATED = "workspace_created"
    WORKSPACE_ACCESSED = "workspace_accessed"
    WORKSPACE_MODIFIED = "workspace_modified"
    WORKSPACE_CLEANED = "workspace_cleaned"


class MCPEventSeverity(Enum):
    """Severity levels for MCP events."""
    
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class MCPEvent:
    """Represents an MCP state transition event."""
    
    event_type: MCPEventType
    id: UUID = field(default_factory=uuid4)
    severity: MCPEventSeverity = field(default=MCPEventSeverity.INFO)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: str = field(default="unknown")  # Which component generated the event
    
    # Event context
    server_name: Optional[str] = None
    tool_name: Optional[str] = None
    agent_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    
    # Event data
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Correlation and tracing
    parent_event_id: Optional[UUID] = None
    correlation_id: Optional[UUID] = None
    trace_id: Optional[UUID] = None
    
    # Timing information
    duration_ms: Optional[float] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "id": str(self.id),
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "server_name": self.server_name,
            "tool_name": self.tool_name,
            "agent_id": str(self.agent_id) if self.agent_id else None,
            "task_id": str(self.task_id) if self.task_id else None,
            "session_id": str(self.session_id) if self.session_id else None,
            "data": self.data,
            "metadata": self.metadata,
            "parent_event_id": str(self.parent_event_id) if self.parent_event_id else None,
            "correlation_id": str(self.correlation_id) if self.correlation_id else None,
            "trace_id": str(self.trace_id) if self.trace_id else None,
            "duration_ms": self.duration_ms,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class EventFilter:
    """Filter for MCP events based on criteria."""
    
    def __init__(
        self,
        event_types: Optional[Set[MCPEventType]] = None,
        severities: Optional[Set[MCPEventSeverity]] = None,
        sources: Optional[Set[str]] = None,
        server_names: Optional[Set[str]] = None,
        agent_ids: Optional[Set[UUID]] = None,
        time_range: Optional[tuple[datetime, datetime]] = None
    ):
        """Initialize event filter.
        
        Args:
            event_types: Set of event types to include
            severities: Set of severities to include
            sources: Set of sources to include
            server_names: Set of server names to include
            agent_ids: Set of agent IDs to include
            time_range: Tuple of (start_time, end_time) for filtering
        """
        self.event_types = event_types
        self.severities = severities
        self.sources = sources
        self.server_names = server_names
        self.agent_ids = agent_ids
        self.time_range = time_range
    
    def matches(self, event: MCPEvent) -> bool:
        """Check if an event matches the filter criteria.
        
        Args:
            event: Event to check
            
        Returns:
            True if event matches all filter criteria
        """
        if self.event_types and event.event_type not in self.event_types:
            return False
        
        if self.severities and event.severity not in self.severities:
            return False
        
        if self.sources and event.source not in self.sources:
            return False
        
        if self.server_names and event.server_name not in self.server_names:
            return False
        
        if self.agent_ids and event.agent_id not in self.agent_ids:
            return False
        
        if self.time_range:
            start_time, end_time = self.time_range
            if not (start_time <= event.timestamp <= end_time):
                return False
        
        return True


class MCPEventHandler:
    """Base class for MCP event handlers."""
    
    async def handle_event(self, event: MCPEvent) -> None:
        """Handle an MCP event.
        
        Args:
            event: Event to handle
        """
        raise NotImplementedError


class LoggingEventHandler(MCPEventHandler):
    """Event handler that logs events using structured logging."""
    
    def __init__(self, logger_name: str = __name__):
        """Initialize logging handler.
        
        Args:
            logger_name: Name for the logger
        """
        self.logger = structlog.get_logger(logger_name)
    
    async def handle_event(self, event: MCPEvent) -> None:
        """Log the event with appropriate severity."""
        log_data = {
            "mcp_event": {
                "id": str(event.id),
                "type": event.event_type.value,
                "source": event.source,
                "server": event.server_name,
                "tool": event.tool_name,
                "agent_id": str(event.agent_id) if event.agent_id else None,
                "task_id": str(event.task_id) if event.task_id else None,
                "duration_ms": event.duration_ms,
                **event.data
            }
        }
        
        # Log with appropriate level
        if event.severity == MCPEventSeverity.DEBUG:
            self.logger.debug(f"MCP: {event.event_type.value}", **log_data)
        elif event.severity == MCPEventSeverity.INFO:
            self.logger.info(f"MCP: {event.event_type.value}", **log_data)
        elif event.severity == MCPEventSeverity.WARNING:
            self.logger.warning(f"MCP: {event.event_type.value}", **log_data)
        elif event.severity == MCPEventSeverity.ERROR:
            self.logger.error(f"MCP: {event.event_type.value}", **log_data)
        elif event.severity == MCPEventSeverity.CRITICAL:
            self.logger.critical(f"MCP: {event.event_type.value}", **log_data)


class MetricsEventHandler(MCPEventHandler):
    """Event handler that emits Prometheus metrics."""
    
    def __init__(self):
        """Initialize metrics handler."""
        self.metrics = get_metrics()
    
    async def handle_event(self, event: MCPEvent) -> None:
        """Emit metrics based on the event."""
        labels = {
            "event_type": event.event_type.value,
            "severity": event.severity.value,
            "source": event.source,
            "server": event.server_name or "unknown",
        }
        
        # Count events
        self.metrics.mcp_events_total.labels(**labels).inc()
        
        # Record duration for timed events
        if event.duration_ms is not None:
            self.metrics.mcp_operation_duration.labels(
                operation=event.event_type.value,
                server=event.server_name or "unknown"
            ).observe(event.duration_ms / 1000.0)  # Convert to seconds
        
        # Handle specific event types
        if event.event_type in [MCPEventType.TOOL_CALL_STARTED, MCPEventType.TOOL_CALL_COMPLETED]:
            tool_labels = {
                "tool": event.tool_name or "unknown",
                "server": event.server_name or "unknown",
                "status": "success" if event.event_type == MCPEventType.TOOL_CALL_COMPLETED else "started"
            }
            self.metrics.mcp_tool_calls_total.labels(**tool_labels).inc()
        
        elif event.event_type == MCPEventType.TOOL_CALL_FAILED:
            tool_labels = {
                "tool": event.tool_name or "unknown",
                "server": event.server_name or "unknown",
                "status": "failed"
            }
            self.metrics.mcp_tool_calls_total.labels(**tool_labels).inc()
        
        elif event.event_type in [MCPEventType.SERVER_STARTED, MCPEventType.SERVER_STOPPED]:
            server_labels = {
                "server": event.server_name or "unknown",
                "status": "started" if event.event_type == MCPEventType.SERVER_STARTED else "stopped"
            }
            self.metrics.mcp_server_status.labels(**server_labels).set(
                1 if event.event_type == MCPEventType.SERVER_STARTED else 0
            )


class MCPEventBus:
    """Central event bus for MCP state transitions."""
    
    def __init__(self):
        """Initialize the event bus."""
        self.handlers: List[MCPEventHandler] = []
        self.filters: List[EventFilter] = []
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.event_history: List[MCPEvent] = []
        self.max_history_size = 10000
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()
        
        # Statistics
        self.event_stats = defaultdict(int)
        self.last_event_time = {}
        
        logger.info("MCP Event Bus initialized")
    
    def add_handler(self, handler: MCPEventHandler) -> None:
        """Add an event handler.
        
        Args:
            handler: Handler to add
        """
        with self._lock:
            self.handlers.append(handler)
        logger.info(f"Added MCP event handler: {type(handler).__name__}")
    
    def remove_handler(self, handler: MCPEventHandler) -> None:
        """Remove an event handler.
        
        Args:
            handler: Handler to remove
        """
        with self._lock:
            if handler in self.handlers:
                self.handlers.remove(handler)
        logger.info(f"Removed MCP event handler: {type(handler).__name__}")
    
    def add_filter(self, filter_obj: EventFilter) -> None:
        """Add an event filter.
        
        Args:
            filter_obj: Filter to add
        """
        with self._lock:
            self.filters.append(filter_obj)
    
    async def emit(self, event: MCPEvent) -> None:
        """Emit an event to all handlers.
        
        Args:
            event: Event to emit
        """
        # Update statistics
        self.event_stats[event.event_type.value] += 1
        self.last_event_time[event.event_type.value] = event.timestamp
        
        # Add to history
        self.event_history.append(event)
        if len(self.event_history) > self.max_history_size:
            self.event_history.pop(0)
        
        # Queue for processing
        await self.event_queue.put(event)
    
    async def start(self) -> None:
        """Start the event bus processor."""
        if self._running:
            return
        
        self._running = True
        self._processor_task = asyncio.create_task(self._process_events())
        logger.info("MCP Event Bus started")
    
    async def stop(self) -> None:
        """Stop the event bus processor."""
        if not self._running:
            return
        
        self._running = False
        
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("MCP Event Bus stopped")
    
    async def _process_events(self) -> None:
        """Process events from the queue."""
        while self._running:
            try:
                # Wait for events with timeout to allow shutdown
                event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
                
                # Apply filters
                if self.filters:
                    if not any(f.matches(event) for f in self.filters):
                        continue
                
                # Send to all handlers
                handlers = list(self.handlers)  # Copy to avoid modification during iteration
                
                for handler in handlers:
                    try:
                        await handler.handle_event(event)
                    except Exception as e:
                        logger.error(
                            "MCP event handler failed",
                            handler=type(handler).__name__,
                            event_type=event.event_type.value,
                            error=str(e)
                        )
                
            except asyncio.TimeoutError:
                # Normal timeout to check if we should continue
                continue
            except Exception as e:
                logger.error("Error processing MCP event", error=str(e))
    
    def get_event_statistics(self) -> Dict[str, Any]:
        """Get event bus statistics.
        
        Returns:
            Dictionary containing statistics
        """
        return {
            "total_events": sum(self.event_stats.values()),
            "event_counts": dict(self.event_stats),
            "last_event_times": {k: v.isoformat() for k, v in self.last_event_time.items()},
            "handlers_count": len(self.handlers),
            "filters_count": len(self.filters),
            "history_size": len(self.event_history),
            "queue_size": self.event_queue.qsize(),
            "running": self._running
        }
    
    def get_recent_events(
        self, 
        limit: int = 100, 
        event_filter: Optional[EventFilter] = None
    ) -> List[MCPEvent]:
        """Get recent events from history.
        
        Args:
            limit: Maximum number of events to return
            event_filter: Optional filter to apply
            
        Returns:
            List of recent events
        """
        events = self.event_history
        
        if event_filter:
            events = [e for e in events if event_filter.matches(e)]
        
        return events[-limit:]


# Event factory functions for common event types
class MCPEventFactory:
    """Factory for creating common MCP events."""
    
    @staticmethod
    def server_started(
        server_name: str,
        capabilities: List[str],
        source: str = "mcp_server"
    ) -> MCPEvent:
        """Create a server started event."""
        return MCPEvent(
            event_type=MCPEventType.SERVER_STARTED,
            severity=MCPEventSeverity.INFO,
            source=source,
            server_name=server_name,
            data={
                "capabilities": capabilities,
                "status": "started"
            }
        )
    
    @staticmethod
    def tool_call_started(
        tool_name: str,
        server_name: str,
        args: Dict[str, Any],
        agent_id: Optional[UUID] = None,
        task_id: Optional[UUID] = None,
        source: str = "mcp_client"
    ) -> MCPEvent:
        """Create a tool call started event."""
        return MCPEvent(
            event_type=MCPEventType.TOOL_CALL_STARTED,
            severity=MCPEventSeverity.DEBUG,
            source=source,
            server_name=server_name,
            tool_name=tool_name,
            agent_id=agent_id,
            task_id=task_id,
            started_at=datetime.utcnow(),
            data={
                "args": args,
                "status": "started"
            }
        )
    
    @staticmethod
    def tool_call_completed(
        tool_name: str,
        server_name: str,
        result: Any,
        duration_ms: float,
        agent_id: Optional[UUID] = None,
        task_id: Optional[UUID] = None,
        source: str = "mcp_client"
    ) -> MCPEvent:
        """Create a tool call completed event."""
        return MCPEvent(
            event_type=MCPEventType.TOOL_CALL_COMPLETED,
            severity=MCPEventSeverity.DEBUG,
            source=source,
            server_name=server_name,
            tool_name=tool_name,
            agent_id=agent_id,
            task_id=task_id,
            completed_at=datetime.utcnow(),
            duration_ms=duration_ms,
            data={
                "result": result,
                "status": "completed"
            }
        )
    
    @staticmethod
    def security_violation(
        violation_type: str,
        details: str,
        server_name: Optional[str] = None,
        agent_id: Optional[UUID] = None,
        source: str = "mcp_security"
    ) -> MCPEvent:
        """Create a security violation event."""
        return MCPEvent(
            event_type=MCPEventType.SECURITY_VIOLATION,
            severity=MCPEventSeverity.ERROR,
            source=source,
            server_name=server_name,
            agent_id=agent_id,
            data={
                "violation_type": violation_type,
                "details": details,
                "status": "blocked"
            }
        )


# Global event bus instance
_event_bus: Optional[MCPEventBus] = None
_bus_lock = threading.Lock()


def get_mcp_event_bus() -> MCPEventBus:
    """Get the global MCP event bus instance.
    
    Returns:
        Global MCPEventBus instance
    """
    global _event_bus
    
    if _event_bus is None:
        with _bus_lock:
            if _event_bus is None:
                _event_bus = MCPEventBus()
                
                # Add default handlers
                _event_bus.add_handler(LoggingEventHandler())
                _event_bus.add_handler(MetricsEventHandler())
    
    return _event_bus


async def emit_mcp_event(event: MCPEvent) -> None:
    """Emit an MCP event to the global event bus.
    
    Args:
        event: Event to emit
    """
    bus = get_mcp_event_bus()
    await bus.emit(event)


async def initialize_mcp_events() -> MCPEventBus:
    """Initialize the MCP event system.
    
    Returns:
        Initialized event bus
    """
    bus = get_mcp_event_bus()
    await bus.start()
    
    logger.info("MCP event system initialized")
    return bus


async def shutdown_mcp_events() -> None:
    """Shutdown the MCP event system."""
    global _event_bus
    
    if _event_bus is not None:
        await _event_bus.stop()
        _event_bus = None
    
    logger.info("MCP event system shutdown")