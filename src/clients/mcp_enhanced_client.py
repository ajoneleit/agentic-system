"""Enhanced MCP Client with comprehensive state transition event tracking.

This module extends the existing MCP client to emit detailed state transition
events for monitoring, debugging, and observability of agent interactions
with MCP servers.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, AsyncGenerator
from uuid import UUID, uuid4

import structlog

from .claude_cli_mcp_client import ClaudeCodeMCPClient, MCPToolUsage
from ..core.mcp_events import (
    MCPEvent, MCPEventType, MCPEventSeverity, MCPEventFactory,
    emit_mcp_event, get_mcp_event_bus
)
from ..utils.observability import PerformanceTracker

logger = structlog.get_logger(__name__)


class EnhancedMCPClient(ClaudeCodeMCPClient):
    """Enhanced MCP client with comprehensive event tracking."""
    
    def __init__(self):
        """Initialize the enhanced MCP client."""
        super().__init__()
        self.performance_tracker = PerformanceTracker()
        self.active_sessions: Dict[str, UUID] = {}  # task_id -> session_id
        self.active_tool_calls: Dict[UUID, Dict[str, Any]] = {}  # call_id -> call_info
        
        logger.info("Enhanced MCP client initialized with event tracking")
    
    async def create_message(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.0,
        system: Optional[str] = None,
        tools: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create a message with comprehensive event tracking."""
        
        # Extract session information
        task_id = kwargs.get("task_id", str(uuid4()))
        agent_id = kwargs.get("agent_id")
        session_id = uuid4()
        
        # Track session start
        self.active_sessions[task_id] = session_id
        
        # Emit agent task started event
        await emit_mcp_event(MCPEvent(
            event_type=MCPEventType.AGENT_TASK_STARTED,
            severity=MCPEventSeverity.INFO,
            source="enhanced_mcp_client",
            agent_id=agent_id,
            task_id=UUID(task_id) if task_id else None,
            session_id=session_id,
            data={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "tools_requested": tools or [],
                "message_count": len(messages)
            }
        ))
        
        try:
            # Track workspace setup
            workspace_path = await self._setup_workspace_with_events(task_id, kwargs.get("workspace_path"))
            kwargs["workspace_path"] = workspace_path
            
            # Execute with performance tracking
            with self.performance_tracker.track_task_execution(
                agent_role=kwargs.get("agent_role", "unknown"),
                task_type="mcp_message_creation",
                task_id=UUID(task_id) if task_id else None
            ):
                result = await super().create_message(
                    model, messages, max_tokens, temperature, system, tools, **kwargs
                )
            
            # Emit completion event
            await emit_mcp_event(MCPEvent(
                event_type=MCPEventType.AGENT_TASK_COMPLETED,
                severity=MCPEventSeverity.INFO,
                source="enhanced_mcp_client",
                agent_id=agent_id,
                task_id=UUID(task_id) if task_id else None,
                session_id=session_id,
                data={
                    "result_tokens": result.get("usage", {}).get("output_tokens", 0),
                    "files_created": len(result.get("metadata", {}).get("files_created", [])),
                    "files_modified": len(result.get("metadata", {}).get("files_modified", [])),
                    "commands_executed": len(result.get("metadata", {}).get("commands_executed", [])),
                    "execution_time": result.get("metadata", {}).get("execution_time", 0)
                }
            ))
            
            return result
            
        except Exception as e:
            # Emit failure event
            await emit_mcp_event(MCPEvent(
                event_type=MCPEventType.AGENT_TASK_FAILED,
                severity=MCPEventSeverity.ERROR,
                source="enhanced_mcp_client",
                agent_id=agent_id,
                task_id=UUID(task_id) if task_id else None,
                session_id=session_id,
                data={
                    "error_type": e.__class__.__name__,
                    "error_message": str(e)
                }
            ))
            raise
        
        finally:
            # Clean up session
            if task_id in self.active_sessions:
                del self.active_sessions[task_id]
    
    async def _setup_workspace_with_events(self, task_id: str, base_path: Optional[str] = None) -> str:
        """Setup workspace with event tracking."""
        
        # Emit workspace creation start
        await emit_mcp_event(MCPEvent(
            event_type=MCPEventType.WORKSPACE_CREATED,
            severity=MCPEventSeverity.INFO,
            source="enhanced_mcp_client",
            task_id=UUID(task_id) if task_id else None,
            data={
                "task_id": task_id,
                "base_path": base_path,
                "status": "creating"
            }
        ))
        
        try:
            workspace_path = await super()._setup_workspace(task_id, base_path)
            
            # Emit workspace created success
            await emit_mcp_event(MCPEvent(
                event_type=MCPEventType.WORKSPACE_CREATED,
                severity=MCPEventSeverity.INFO,
                source="enhanced_mcp_client",
                task_id=UUID(task_id) if task_id else None,
                data={
                    "task_id": task_id,
                    "workspace_path": str(workspace_path),
                    "status": "created"
                }
            ))
            
            return workspace_path
            
        except Exception as e:
            # Emit workspace creation failure
            await emit_mcp_event(MCPEvent(
                event_type=MCPEventType.WORKSPACE_CREATED,
                severity=MCPEventSeverity.ERROR,
                source="enhanced_mcp_client",
                task_id=UUID(task_id) if task_id else None,
                data={
                    "task_id": task_id,
                    "error": str(e),
                    "status": "failed"
                }
            ))
            raise
    
    @asynccontextmanager
    async def track_tool_call(
        self,
        tool_name: str,
        server_name: str,
        args: Dict[str, Any],
        agent_id: Optional[UUID] = None,
        task_id: Optional[UUID] = None
    ) -> AsyncGenerator[UUID, None]:
        """Context manager for tracking tool calls with events."""
        
        call_id = uuid4()
        start_time = time.time()
        
        # Store call info
        self.active_tool_calls[call_id] = {
            "tool_name": tool_name,
            "server_name": server_name,
            "args": args,
            "start_time": start_time,
            "agent_id": agent_id,
            "task_id": task_id
        }
        
        # Emit start event
        start_event = MCPEventFactory.tool_call_started(
            tool_name=tool_name,
            server_name=server_name,
            args=args,
            agent_id=agent_id,
            task_id=task_id,
            source="enhanced_mcp_client"
        )
        await emit_mcp_event(start_event)
        
        try:
            yield call_id
            
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Emit completion event
            completion_event = MCPEventFactory.tool_call_completed(
                tool_name=tool_name,
                server_name=server_name,
                result={"status": "success"},
                duration_ms=duration_ms,
                agent_id=agent_id,
                task_id=task_id,
                source="enhanced_mcp_client"
            )
            await emit_mcp_event(completion_event)
            
        except asyncio.TimeoutError:
            # Emit timeout event
            await emit_mcp_event(MCPEvent(
                event_type=MCPEventType.TOOL_CALL_TIMEOUT,
                severity=MCPEventSeverity.WARNING,
                source="enhanced_mcp_client",
                server_name=server_name,
                tool_name=tool_name,
                agent_id=agent_id,
                task_id=task_id,
                duration_ms=(time.time() - start_time) * 1000,
                data={
                    "args": args,
                    "timeout_reason": "operation_timeout"
                }
            ))
            raise
            
        except Exception as e:
            # Emit failure event
            await emit_mcp_event(MCPEvent(
                event_type=MCPEventType.TOOL_CALL_FAILED,
                severity=MCPEventSeverity.ERROR,
                source="enhanced_mcp_client",
                server_name=server_name,
                tool_name=tool_name,
                agent_id=agent_id,
                task_id=task_id,
                duration_ms=(time.time() - start_time) * 1000,
                data={
                    "args": args,
                    "error_type": e.__class__.__name__,
                    "error_message": str(e)
                }
            ))
            raise
            
        finally:
            # Clean up call tracking
            if call_id in self.active_tool_calls:
                del self.active_tool_calls[call_id]
    
    async def start_server_with_events(self, server_name: str, server_config: Dict[str, Any]) -> None:
        """Start an MCP server with event tracking."""
        
        # Emit server starting event
        await emit_mcp_event(MCPEvent(
            event_type=MCPEventType.SERVER_STARTING,
            severity=MCPEventSeverity.INFO,
            source="enhanced_mcp_client",
            server_name=server_name,
            data={
                "command": server_config.get("command", ""),
                "args": server_config.get("args", []),
                "capabilities": server_config.get("capabilities", [])
            }
        ))
        
        try:
            # Simulate server startup (would be actual server management in real implementation)
            await asyncio.sleep(0.1)  # Simulate startup time
            
            # Emit server started event
            started_event = MCPEventFactory.server_started(
                server_name=server_name,
                capabilities=server_config.get("capabilities", []),
                source="enhanced_mcp_client"
            )
            await emit_mcp_event(started_event)
            
            # Emit connection established event
            await emit_mcp_event(MCPEvent(
                event_type=MCPEventType.CONNECTION_ESTABLISHED,
                severity=MCPEventSeverity.INFO,
                source="enhanced_mcp_client",
                server_name=server_name,
                data={
                    "connection_type": "mcp",
                    "protocol_version": "1.0"
                }
            ))
            
        except Exception as e:
            # Emit server error event
            await emit_mcp_event(MCPEvent(
                event_type=MCPEventType.SERVER_ERROR,
                severity=MCPEventSeverity.ERROR,
                source="enhanced_mcp_client",
                server_name=server_name,
                data={
                    "error_type": e.__class__.__name__,
                    "error_message": str(e)
                }
            ))
            raise
    
    async def stop_server_with_events(self, server_name: str) -> None:
        """Stop an MCP server with event tracking."""
        
        # Emit server stopping event
        await emit_mcp_event(MCPEvent(
            event_type=MCPEventType.SERVER_STOPPING,
            severity=MCPEventSeverity.INFO,
            source="enhanced_mcp_client",
            server_name=server_name,
            data={"reason": "shutdown_requested"}
        ))
        
        try:
            # Simulate server shutdown
            await asyncio.sleep(0.1)
            
            # Emit connection closed event
            await emit_mcp_event(MCPEvent(
                event_type=MCPEventType.CONNECTION_CLOSED,
                severity=MCPEventSeverity.INFO,
                source="enhanced_mcp_client",
                server_name=server_name,
                data={"reason": "clean_shutdown"}
            ))
            
            # Emit server stopped event
            await emit_mcp_event(MCPEvent(
                event_type=MCPEventType.SERVER_STOPPED,
                severity=MCPEventSeverity.INFO,
                source="enhanced_mcp_client",
                server_name=server_name,
                data={"shutdown_clean": True}
            ))
            
        except Exception as e:
            # Emit server crash event
            await emit_mcp_event(MCPEvent(
                event_type=MCPEventType.SERVER_CRASHED,
                severity=MCPEventSeverity.ERROR,
                source="enhanced_mcp_client",
                server_name=server_name,
                data={
                    "error_type": e.__class__.__name__,
                    "error_message": str(e)
                }
            ))
            raise
    
    async def handle_security_check(
        self,
        operation: str,
        resource_path: str,
        agent_id: Optional[UUID] = None,
        server_name: Optional[str] = None
    ) -> bool:
        """Handle security checks with event tracking.
        
        Args:
            operation: Operation being performed (read, write, execute, etc.)
            resource_path: Path to the resource being accessed
            agent_id: ID of the agent requesting access
            server_name: Name of the MCP server
            
        Returns:
            True if access is granted, False otherwise
        """
        
        # Simple security check (would be more sophisticated in real implementation)
        allowed_paths = ["/workspace", "/artifacts", "/tests", "/src"]
        denied_paths = ["/etc", "/usr", "/bin", "/sbin", "/home"]
        
        # Check if path is allowed
        access_granted = any(resource_path.startswith(allowed) for allowed in allowed_paths)
        access_denied = any(resource_path.startswith(denied) for denied in denied_paths)
        
        if access_denied:
            access_granted = False
        
        if access_granted:
            # Emit permission granted event
            await emit_mcp_event(MCPEvent(
                event_type=MCPEventType.PERMISSION_GRANTED,
                severity=MCPEventSeverity.DEBUG,
                source="enhanced_mcp_client",
                server_name=server_name,
                agent_id=agent_id,
                data={
                    "operation": operation,
                    "resource_path": resource_path,
                    "decision": "granted"
                }
            ))
        else:
            # Emit permission denied event
            await emit_mcp_event(MCPEvent(
                event_type=MCPEventType.PERMISSION_DENIED,
                severity=MCPEventSeverity.WARNING,
                source="enhanced_mcp_client",
                server_name=server_name,
                agent_id=agent_id,
                data={
                    "operation": operation,
                    "resource_path": resource_path,
                    "decision": "denied",
                    "reason": "path_not_allowed"
                }
            ))
            
            # Check if this is a security violation
            if access_denied:
                violation_event = MCPEventFactory.security_violation(
                    violation_type="unauthorized_path_access",
                    details=f"Attempted {operation} on {resource_path}",
                    server_name=server_name,
                    agent_id=agent_id,
                    source="enhanced_mcp_client"
                )
                await emit_mcp_event(violation_event)
        
        return access_granted
    
    async def track_resource_operation(
        self,
        operation_type: str,
        resource_path: str,
        server_name: Optional[str] = None,
        agent_id: Optional[UUID] = None
    ) -> None:
        """Track resource operations with events.
        
        Args:
            operation_type: Type of operation (created, modified, deleted, accessed)
            resource_path: Path to the resource
            server_name: Name of the MCP server
            agent_id: ID of the agent performing the operation
        """
        
        event_type_map = {
            "created": MCPEventType.RESOURCE_CREATED,
            "modified": MCPEventType.RESOURCE_MODIFIED,
            "deleted": MCPEventType.RESOURCE_DELETED,
            "accessed": MCPEventType.RESOURCE_ACCESSED
        }
        
        event_type = event_type_map.get(operation_type, MCPEventType.RESOURCE_ACCESSED)
        
        await emit_mcp_event(MCPEvent(
            event_type=event_type,
            severity=MCPEventSeverity.DEBUG,
            source="enhanced_mcp_client",
            server_name=server_name,
            agent_id=agent_id,
            data={
                "resource_path": resource_path,
                "operation": operation_type
            }
        ))
    
    async def get_client_statistics(self) -> Dict[str, Any]:
        """Get client statistics including event data.
        
        Returns:
            Dictionary containing client statistics
        """
        event_bus = get_mcp_event_bus()
        event_stats = event_bus.get_event_statistics()
        
        return {
            "active_sessions": len(self.active_sessions),
            "active_tool_calls": len(self.active_tool_calls),
            "workspaces_managed": len(self._workspaces),
            "event_bus_stats": event_stats,
            "recent_events": len(event_bus.get_recent_events(limit=50))
        }
    
    async def close(self):
        """Close the client with event tracking."""
        
        # Emit shutdown events for any active sessions
        for task_id, session_id in self.active_sessions.items():
            await emit_mcp_event(MCPEvent(
                event_type=MCPEventType.AGENT_TASK_COMPLETED,
                severity=MCPEventSeverity.INFO,
                source="enhanced_mcp_client",
                task_id=UUID(task_id) if task_id else None,
                session_id=session_id,
                data={
                    "shutdown_reason": "client_close",
                    "forced_termination": True
                }
            ))
        
        # Call parent close
        await super().close()
        
        logger.info("Enhanced MCP client closed with event tracking")