"""Agent coordination and lifecycle management for the Agentic Coding System.

This module handles agent spawning, monitoring, resource allocation, and
overall system coordination.
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Type
from uuid import UUID, uuid4

from structlog import get_logger

from config import get_settings
from src.core.communication import CommunicationHub, MessageType, MessagePriority
from src.core.exceptions import (
    AgentError,
    AgentInitializationError,
    AgentOverloadError,
)
from src.core.interfaces import (
    Agent,
    AgentRole,
    Task,
    TaskContext,
    TaskStatus,
)
from src.core.task_manager import TaskManager


logger = get_logger(__name__)


class AgentStatus(str, Enum):
    """Status of an agent in the system."""
    
    IDLE = "idle"
    INITIALIZING = "initializing"
    WORKING = "working"
    STUCK = "stuck"
    WAITING = "waiting"
    PAUSED = "paused"
    ERROR = "error"
    TIMEOUT = "timeout"
    SHUTTING_DOWN = "shutting_down"
    TERMINATED = "terminated"


class ResourceType(str, Enum):
    """Types of resources agents can consume."""
    
    API_CALLS = "api_calls"
    MEMORY = "memory"
    TASKS = "tasks"
    TIME = "time"


@dataclass
class AgentMetrics:
    """Metrics for agent performance tracking."""
    
    agent_id: UUID
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_execution_time: float = 0.0
    average_task_time: float = 0.0
    success_rate: float = 1.0
    api_calls_made: int = 0
    errors_encountered: int = 0
    last_activity: datetime = field(default_factory=datetime.utcnow)
    
    # Enhanced progress tracking
    current_operation: str = "idle"
    operation_start_time: Optional[datetime] = None
    progress_percentage: float = 0.0
    heartbeat_count: int = 0
    last_heartbeat: datetime = field(default_factory=datetime.utcnow)
    stuck_detection_count: int = 0
    recovery_attempts: int = 0
    
    # Resource monitoring
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    
    def update_task_completion(self, success: bool, execution_time: float) -> None:
        """Update metrics after task completion."""
        if success:
            self.tasks_completed += 1
        else:
            self.tasks_failed += 1
        
        self.total_execution_time += execution_time
        total_tasks = self.tasks_completed + self.tasks_failed
        self.average_task_time = self.total_execution_time / total_tasks if total_tasks > 0 else 0
        self.success_rate = self.tasks_completed / total_tasks if total_tasks > 0 else 1.0
        self.last_activity = datetime.utcnow()
        
        # Reset operation tracking
        self.current_operation = "idle"
        self.operation_start_time = None
        self.progress_percentage = 0.0
    
    def start_operation(self, operation: str) -> None:
        """Start tracking a new operation."""
        self.current_operation = operation
        self.operation_start_time = datetime.utcnow()
        self.progress_percentage = 0.0
        self.last_activity = datetime.utcnow()
    
    def update_progress(self, percentage: float, operation: Optional[str] = None) -> None:
        """Update progress for current operation."""
        self.progress_percentage = min(100.0, max(0.0, percentage))
        self.last_activity = datetime.utcnow()
        if operation:
            self.current_operation = operation
    
    def heartbeat(self) -> None:
        """Record agent heartbeat."""
        self.heartbeat_count += 1
        self.last_heartbeat = datetime.utcnow()
        self.last_activity = datetime.utcnow()
    
    def record_stuck_detection(self) -> None:
        """Record stuck agent detection."""
        self.stuck_detection_count += 1
    
    def record_recovery_attempt(self) -> None:
        """Record recovery attempt."""
        self.recovery_attempts += 1
    
    def update_resource_usage(self, memory_mb: float, cpu_percent: float) -> None:
        """Update resource usage metrics."""
        self.memory_usage_mb = memory_mb
        self.cpu_usage_percent = cpu_percent
    
    def get_operation_duration(self) -> float:
        """Get duration of current operation in seconds."""
        if self.operation_start_time:
            return (datetime.utcnow() - self.operation_start_time).total_seconds()
        return 0.0
    
    def is_stuck(self, timeout_seconds: float = 300) -> bool:
        """Check if agent appears to be stuck."""
        if self.current_operation == "idle":
            return False
        
        # Check if operation has been running too long
        operation_duration = self.get_operation_duration()
        if operation_duration > timeout_seconds:
            return True
        
        # Check if heartbeat is too old
        heartbeat_age = (datetime.utcnow() - self.last_heartbeat).total_seconds()
        if heartbeat_age > 60:  # No heartbeat for 1 minute
            return True
        
        return False


class ResourceManager:
    """Manages resource allocation and limits for agents."""
    
    def __init__(self):
        """Initialize resource manager."""
        self._allocations: Dict[UUID, Dict[ResourceType, float]] = defaultdict(lambda: defaultdict(float))
        self._limits: Dict[ResourceType, float] = {
            ResourceType.API_CALLS: 1000,  # Per hour
            ResourceType.MEMORY: 1024,  # MB
            ResourceType.TASKS: 10,  # Concurrent
            ResourceType.TIME: 3600,  # Seconds per task
        }
        self._usage: Dict[UUID, Dict[ResourceType, float]] = defaultdict(lambda: defaultdict(float))
        self._lock = asyncio.Lock()
    
    async def allocate(
        self,
        agent_id: UUID,
        resource: ResourceType,
        amount: float
    ) -> bool:
        """Allocate resources to an agent.
        
        Args:
            agent_id: Agent requesting resources
            resource: Type of resource
            amount: Amount to allocate
            
        Returns:
            True if allocated successfully
        """
        async with self._lock:
            current_usage = sum(
                alloc[resource] for alloc in self._allocations.values()
            )
            
            if current_usage + amount > self._limits[resource]:
                logger.warning(
                    "Resource allocation denied",
                    agent_id=str(agent_id),
                    resource=resource.value,
                    requested=amount,
                    available=self._limits[resource] - current_usage,
                )
                return False
            
            self._allocations[agent_id][resource] += amount
            return True
    
    async def release(
        self,
        agent_id: UUID,
        resource: ResourceType,
        amount: float
    ) -> None:
        """Release allocated resources.
        
        Args:
            agent_id: Agent releasing resources
            resource: Type of resource
            amount: Amount to release
        """
        async with self._lock:
            if agent_id in self._allocations:
                self._allocations[agent_id][resource] = max(
                    0, self._allocations[agent_id][resource] - amount
                )
    
    async def track_usage(
        self,
        agent_id: UUID,
        resource: ResourceType,
        amount: float
    ) -> None:
        """Track resource usage by an agent.
        
        Args:
            agent_id: Agent using resources
            resource: Type of resource
            amount: Amount used
        """
        async with self._lock:
            self._usage[agent_id][resource] += amount
    
    async def get_usage_report(self, agent_id: UUID) -> Dict[str, Any]:
        """Get resource usage report for an agent.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Usage report
        """
        async with self._lock:
            return {
                "allocations": dict(self._allocations.get(agent_id, {})),
                "usage": dict(self._usage.get(agent_id, {})),
                "limits": dict(self._limits),
            }
    
    async def cleanup_agent(self, agent_id: UUID) -> None:
        """Clean up resources for a terminated agent.
        
        Args:
            agent_id: Agent ID
        """
        async with self._lock:
            self._allocations.pop(agent_id, None)
            self._usage.pop(agent_id, None)


class AgentCoordinator:
    """Coordinates agent lifecycle and system-wide operations."""
    
    def __init__(
        self,
        task_manager: TaskManager,
        communication_hub: CommunicationHub,
        max_agents: int = 20
    ):
        """Initialize agent coordinator.
        
        Args:
            task_manager: Task management system
            communication_hub: Communication system
            max_agents: Maximum concurrent agents
        """
        self.task_manager = task_manager
        self.communication_hub = communication_hub
        self.max_agents = max_agents
        
        self._agents: Dict[UUID, Agent] = {}
        self._agent_status: Dict[UUID, AgentStatus] = {}
        self._agent_metrics: Dict[UUID, AgentMetrics] = {}
        self._agent_tasks: Dict[UUID, Set[UUID]] = defaultdict(set)
        self._agent_factories: Dict[AgentRole, Type[Agent]] = {}
        
        self.resource_manager = ResourceManager()
        self._monitoring_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
        logger.info(
            "Agent coordinator initialized",
            max_agents=max_agents,
        )
    
    def register_agent_factory(
        self,
        role: AgentRole,
        factory: Type[Agent]
    ) -> None:
        """Register a factory for creating agents of a specific role.
        
        Args:
            role: Agent role
            factory: Agent class or factory function
        """
        self._agent_factories[role] = factory
        logger.info(f"Registered agent factory for role: {role.value}")
    
    async def spawn_agent(
        self,
        role: AgentRole,
        context: TaskContext,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Agent:
        """Spawn a new agent with the specified role.
        
        Args:
            role: Role for the agent
            context: Execution context
            metadata: Optional agent metadata
            
        Returns:
            Spawned agent instance
            
        Raises:
            AgentInitializationError: If agent cannot be created
            AgentOverloadError: If max agents reached
        """
        async with self._lock:
            if len(self._agents) >= self.max_agents:
                raise AgentOverloadError(
                    agent_id=uuid4(),
                    current_tasks=len(self._agents),
                    max_tasks=self.max_agents
                )
            
            if role not in self._agent_factories:
                raise AgentInitializationError(
                    agent_id=uuid4(),
                    role=role.value,
                    reason=f"No factory registered for role {role.value}"
                )
        
        try:
            # Create agent instance
            agent_id = uuid4()
            agent_class = self._agent_factories[role]
            # Note: Sub-agent classes hardcode their role, so we only pass agent_id
            agent = agent_class(agent_id=agent_id)
            
            # Initialize agent
            self._agent_status[agent_id] = AgentStatus.INITIALIZING
            await agent.initialize(context)
            
            # Register with systems
            async with self._lock:
                self._agents[agent_id] = agent
                self._agent_status[agent_id] = AgentStatus.IDLE
                self._agent_metrics[agent_id] = AgentMetrics(agent_id=agent_id)
            
            # Register with communication hub
            await self.communication_hub.register_agent(agent, metadata)
            
            # Allocate initial resources
            await self.resource_manager.allocate(
                agent_id,
                ResourceType.TASKS,
                1
            )
            
            logger.info(
                "Agent spawned successfully",
                agent_id=str(agent_id),
                role=role.value,
            )
            
            return agent
            
        except Exception as e:
            logger.error(
                "Failed to spawn agent",
                role=role.value,
                error=str(e),
                exc_info=True,
            )
            raise AgentInitializationError(
                agent_id=agent_id if 'agent_id' in locals() else uuid4(),
                role=role.value,
                reason=str(e)
            )
    
    async def assign_task(self, agent_id: UUID, task: Task) -> None:
        """Assign a task to an agent.
        
        Args:
            agent_id: Agent to assign to
            task: Task to assign
            
        Raises:
            AgentError: If agent not found or cannot accept task
        """
        async with self._lock:
            if agent_id not in self._agents:
                raise AgentError(
                    agent_id=agent_id,
                    message="Agent not found"
                )
            
            agent = self._agents[agent_id]
            status = self._agent_status[agent_id]
            
            if status not in [AgentStatus.IDLE, AgentStatus.WORKING]:
                raise AgentError(
                    agent_id=agent_id,
                    message=f"Agent in {status.value} state cannot accept tasks"
                )
            
            # Check resource limits
            current_tasks = len(self._agent_tasks[agent_id])
            if current_tasks >= 5:  # Max tasks per agent
                raise AgentOverloadError(
                    agent_id=agent_id,
                    current_tasks=current_tasks,
                    max_tasks=5
                )
            
            self._agent_tasks[agent_id].add(task.id)
            self._agent_status[agent_id] = AgentStatus.WORKING
        
        # Notify agent of task assignment
        await self.communication_hub.send_message(
            sender_id=uuid4(),  # System ID
            receiver_id=agent_id,
            message_type=MessageType.TASK_REQUEST,
            content={
                "task": task.model_dump(),
                "deadline": (datetime.utcnow() + timedelta(minutes=30)).isoformat(),
            },
            priority=MessagePriority.HIGH,
            requires_response=True
        )
        
        logger.info(
            "Task assigned to agent",
            agent_id=str(agent_id),
            task_id=str(task.id),
            task_name=task.name,
        )
    
    async def monitor_agents(self) -> None:
        """Monitor agent health and performance with comprehensive stuck detection."""
        while True:
            try:
                await asyncio.sleep(5)  # Check every 5 seconds for better responsiveness
                
                async with self._lock:
                    agents_to_check = list(self._agents.items())
                
                system_metrics = {
                    "total_agents": len(agents_to_check),
                    "active_agents": 0,
                    "stuck_agents": 0,
                    "idle_agents": 0,
                    "working_agents": 0,
                    "failed_agents": 0
                }
                
                for agent_id, agent in agents_to_check:
                    try:
                        # Get agent status and metrics
                        status_report = await agent.report_status()
                        metrics = self._agent_metrics.get(agent_id)
                        current_status = self._agent_status.get(agent_id, AgentStatus.IDLE)
                        
                        if metrics:
                            # Update heartbeat
                            metrics.heartbeat()
                            
                            # Update resource usage (mock data - in production would get real metrics)
                            import psutil
                            try:
                                process = psutil.Process()
                                memory_mb = process.memory_info().rss / 1024 / 1024
                                cpu_percent = process.cpu_percent()
                                metrics.update_resource_usage(memory_mb, cpu_percent)
                            except:
                                pass  # Gracefully handle if psutil not available
                            
                            # Check for stuck agents
                            if metrics.is_stuck():
                                if current_status != AgentStatus.STUCK:
                                    logger.warning(
                                        "Agent stuck detected",
                                        agent_id=str(agent_id),
                                        current_operation=metrics.current_operation,
                                        operation_duration=metrics.get_operation_duration(),
                                        last_heartbeat_age=(datetime.utcnow() - metrics.last_heartbeat).total_seconds(),
                                        stuck_detection_count=metrics.stuck_detection_count
                                    )
                                    
                                    # Update status to stuck
                                    self._agent_status[agent_id] = AgentStatus.STUCK
                                    metrics.record_stuck_detection()
                                    
                                    # Attempt recovery
                                    await self._handle_stuck_agent(agent_id)
                                    
                                system_metrics["stuck_agents"] += 1
                            
                            # Update system metrics
                            if current_status == AgentStatus.WORKING:
                                system_metrics["working_agents"] += 1
                                system_metrics["active_agents"] += 1
                            elif current_status == AgentStatus.IDLE:
                                system_metrics["idle_agents"] += 1
                            elif current_status in [AgentStatus.ERROR, AgentStatus.TIMEOUT]:
                                system_metrics["failed_agents"] += 1
                            
                            # Log detailed agent activity
                            logger.info(
                                "Agent monitoring update",
                                agent_id=str(agent_id),
                                status=current_status.value,
                                current_operation=metrics.current_operation,
                                progress=metrics.progress_percentage,
                                operation_duration=metrics.get_operation_duration(),
                                heartbeat_count=metrics.heartbeat_count,
                                memory_mb=metrics.memory_usage_mb,
                                cpu_percent=metrics.cpu_usage_percent,
                                tasks_completed=metrics.tasks_completed,
                                success_rate=metrics.success_rate
                            )
                        
                    except Exception as e:
                        logger.error(
                            "Error monitoring agent",
                            agent_id=str(agent_id),
                            error=str(e),
                        )
                        
                        # Mark agent as error state
                        self._agent_status[agent_id] = AgentStatus.ERROR
                        system_metrics["failed_agents"] += 1
                
                # Log system-wide progress
                logger.info(
                    "System monitoring update",
                    **system_metrics
                )
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Monitor loop error", error=str(e))
    
    async def _handle_stuck_agent(self, agent_id: UUID) -> None:
        """Handle an agent that appears to be stuck with comprehensive recovery.
        
        Args:
            agent_id: ID of stuck agent
        """
        metrics = self._agent_metrics.get(agent_id)
        if not metrics:
            return
            
        metrics.record_recovery_attempt()
        
        logger.warning(
            "Attempting stuck agent recovery",
            agent_id=str(agent_id),
            recovery_attempt=metrics.recovery_attempts,
            current_operation=metrics.current_operation,
            operation_duration=metrics.get_operation_duration()
        )
        
        # Recovery strategy based on attempt count
        if metrics.recovery_attempts == 1:
            # First attempt: Send pause request
            await self.communication_hub.send_message(
                sender_id=uuid4(),
                receiver_id=agent_id,
                message_type=MessageType.PAUSE_REQUEST,
                content={"reason": "Agent appears stuck - pause requested"},
                priority=MessagePriority.URGENT
            )
            
            # Update status
            async with self._lock:
                self._agent_status[agent_id] = AgentStatus.PAUSED
                
            logger.info(
                "Stuck agent recovery - pause requested",
                agent_id=str(agent_id),
                recovery_attempt=metrics.recovery_attempts
            )
            
        elif metrics.recovery_attempts == 2:
            # Second attempt: Send resume request after pause
            await asyncio.sleep(2)  # Brief pause
            
            await self.communication_hub.send_message(
                sender_id=uuid4(),
                receiver_id=agent_id,
                message_type=MessageType.RESUME_REQUEST,
                content={"reason": "Resume after stuck detection"},
                priority=MessagePriority.URGENT
            )
            
            # Reset operation tracking
            metrics.current_operation = "resuming"
            metrics.operation_start_time = datetime.utcnow()
            metrics.progress_percentage = 0.0
            
            async with self._lock:
                self._agent_status[agent_id] = AgentStatus.WORKING
                
            logger.info(
                "Stuck agent recovery - resume requested",
                agent_id=str(agent_id),
                recovery_attempt=metrics.recovery_attempts
            )
            
        elif metrics.recovery_attempts >= 3:
            # Third attempt and beyond: Restart agent
            logger.error(
                "Agent stuck - attempting restart",
                agent_id=str(agent_id),
                recovery_attempt=metrics.recovery_attempts
            )
            
            try:
                # Get agent instance
                agent = self._agents.get(agent_id)
                if agent:
                    # Attempt graceful shutdown
                    await agent.shutdown()
                    
                    # Remove from tracking
                    async with self._lock:
                        self._agents.pop(agent_id, None)
                        self._agent_status[agent_id] = AgentStatus.TERMINATED
                        
                    # Clean up resources
                    await self.resource_manager.cleanup_agent(agent_id)
                    
                    logger.info(
                        "Stuck agent terminated for restart",
                        agent_id=str(agent_id),
                        recovery_attempt=metrics.recovery_attempts
                    )
                    
                    # TODO: In a full implementation, we would respawn the agent here
                    # For now, we mark it as terminated
                    
            except Exception as e:
                logger.error(
                    "Failed to restart stuck agent",
                    agent_id=str(agent_id),
                    error=str(e)
                )
                
                # Mark as error state
                async with self._lock:
                    self._agent_status[agent_id] = AgentStatus.ERROR
    
    async def handle_task_completion(
        self,
        agent_id: UUID,
        task_id: UUID,
        success: bool,
        execution_time: float
    ) -> None:
        """Handle task completion by an agent.
        
        Args:
            agent_id: Agent that completed the task
            task_id: Completed task ID
            success: Whether task succeeded
            execution_time: Time taken to complete
        """
        async with self._lock:
            # Update agent tasks
            if agent_id in self._agent_tasks:
                self._agent_tasks[agent_id].discard(task_id)
                
                # Update status if no more tasks
                if not self._agent_tasks[agent_id]:
                    self._agent_status[agent_id] = AgentStatus.IDLE
            
            # Update metrics
            if agent_id in self._agent_metrics:
                self._agent_metrics[agent_id].update_task_completion(
                    success, execution_time
                )
        
        # Release task resource
        await self.resource_manager.release(
            agent_id,
            ResourceType.TASKS,
            1
        )
        
        logger.info(
            "Agent completed task",
            agent_id=str(agent_id),
            task_id=str(task_id),
            success=success,
            execution_time=execution_time,
        )
    
    async def terminate_agent(self, agent_id: UUID) -> None:
        """Terminate an agent gracefully.
        
        Args:
            agent_id: Agent to terminate
        """
        async with self._lock:
            if agent_id not in self._agents:
                return
            
            agent = self._agents[agent_id]
            self._agent_status[agent_id] = AgentStatus.SHUTTING_DOWN
        
        try:
            # Notify agent to shutdown
            await agent.shutdown()
            
            # Unregister from communication
            await self.communication_hub.unregister_agent(agent_id)
            
            # Clean up resources
            await self.resource_manager.cleanup_agent(agent_id)
            
            # Remove from tracking
            async with self._lock:
                self._agents.pop(agent_id, None)
                self._agent_status[agent_id] = AgentStatus.TERMINATED
                self._agent_tasks.pop(agent_id, None)
            
            logger.info("Agent terminated", agent_id=str(agent_id))
            
        except Exception as e:
            logger.error(
                "Error terminating agent",
                agent_id=str(agent_id),
                error=str(e),
            )
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status with comprehensive monitoring data.
        
        Returns:
            System status report
        """
        async with self._lock:
            status_counts = defaultdict(int)
            for status in self._agent_status.values():
                status_counts[status.value] += 1
            
            total_tasks = sum(len(tasks) for tasks in self._agent_tasks.values())
            
            # Calculate system-wide metrics
            total_stuck_detections = sum(m.stuck_detection_count for m in self._agent_metrics.values())
            total_recovery_attempts = sum(m.recovery_attempts for m in self._agent_metrics.values())
            avg_success_rate = sum(m.success_rate for m in self._agent_metrics.values()) / len(self._agent_metrics) if self._agent_metrics else 0
            
            return {
                "total_agents": len(self._agents),
                "max_agents": self.max_agents,
                "agent_status_breakdown": dict(status_counts),
                "total_active_tasks": total_tasks,
                "system_metrics": {
                    "total_stuck_detections": total_stuck_detections,
                    "total_recovery_attempts": total_recovery_attempts,
                    "average_success_rate": avg_success_rate,
                    "agents_with_issues": len([m for m in self._agent_metrics.values() if m.stuck_detection_count > 0])
                },
                "agents": [
                    {
                        "id": str(agent_id),
                        "role": agent.role.value,
                        "status": self._agent_status[agent_id].value,
                        "tasks": len(self._agent_tasks.get(agent_id, set())),
                        "metrics": {
                            "tasks_completed": metrics.tasks_completed,
                            "tasks_failed": metrics.tasks_failed,
                            "success_rate": metrics.success_rate,
                            "average_task_time": metrics.average_task_time,
                            "current_operation": metrics.current_operation,
                            "operation_duration": metrics.get_operation_duration(),
                            "progress_percentage": metrics.progress_percentage,
                            "heartbeat_count": metrics.heartbeat_count,
                            "last_heartbeat_age": (datetime.utcnow() - metrics.last_heartbeat).total_seconds(),
                            "stuck_detection_count": metrics.stuck_detection_count,
                            "recovery_attempts": metrics.recovery_attempts,
                            "memory_usage_mb": metrics.memory_usage_mb,
                            "cpu_usage_percent": metrics.cpu_usage_percent,
                            "is_stuck": metrics.is_stuck()
                        } if (metrics := self._agent_metrics.get(agent_id)) else {}
                    }
                    for agent_id, agent in self._agents.items()
                ],
            }
    
    async def start(self) -> None:
        """Start the coordinator."""
        if not self._monitoring_task:
            self._monitoring_task = asyncio.create_task(self.monitor_agents())
            logger.info("Agent coordinator started")
    
    async def stop(self) -> None:
        """Stop the coordinator and clean up."""
        # Cancel monitoring
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Terminate all agents
        agent_ids = list(self._agents.keys())
        for agent_id in agent_ids:
            await self.terminate_agent(agent_id)
        
        logger.info("Agent coordinator stopped")