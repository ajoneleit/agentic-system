"""Inter-agent communication system for the Agentic Coding System.

This module provides message passing, event notification, and shared context
management for agents to collaborate effectively.
"""

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

from structlog import get_logger

from src.core.interfaces import Agent

logger = get_logger(__name__)


class MessageType(str, Enum):
    """Types of messages agents can exchange."""

    # Task-related messages
    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    TASK_UPDATE = "task_update"

    # Collaboration messages
    ARTIFACT_SHARE = "artifact_share"
    HELP_REQUEST = "help_request"
    HELP_RESPONSE = "help_response"

    # Status messages
    STATUS_UPDATE = "status_update"
    PROGRESS_REPORT = "progress_report"

    # Control messages
    PAUSE_REQUEST = "pause_request"
    RESUME_REQUEST = "resume_request"
    CANCEL_REQUEST = "cancel_request"

    # Broadcast messages
    ANNOUNCEMENT = "announcement"
    WARNING = "warning"
    ERROR = "error"


class MessagePriority(str, Enum):
    """Message priority levels."""

    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class Message:
    """Represents a message between agents."""

    id: UUID = field(default_factory=uuid4)
    sender_id: UUID = field(default_factory=uuid4)
    receiver_id: Optional[UUID] = None  # None for broadcasts
    message_type: MessageType = MessageType.TASK_UPDATE
    priority: MessagePriority = MessagePriority.NORMAL
    subject: str = ""
    content: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    requires_response: bool = False
    correlation_id: Optional[UUID] = None  # For linking related messages

    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary."""
        return {
            "id": str(self.id),
            "sender_id": str(self.sender_id),
            "receiver_id": str(self.receiver_id) if self.receiver_id else None,
            "message_type": self.message_type.value,
            "priority": self.priority.value,
            "subject": self.subject,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "requires_response": self.requires_response,
            "correlation_id": str(self.correlation_id) if self.correlation_id else None,
        }


class MessageBus:
    """Central message bus for agent communication."""

    def __init__(self):
        """Initialize message bus."""
        self._subscribers: dict[MessageType, set[UUID]] = defaultdict(set)
        self._message_handlers: dict[UUID, Callable] = {}
        self._message_queue: dict[UUID, deque] = defaultdict(deque)
        self._broadcast_history: deque = deque(maxlen=100)
        self._lock = asyncio.Lock()

        logger.info("Message bus initialized")

    async def register_agent(
        self,
        agent_id: UUID,
        handler: Callable[[Message], Any],
        subscribed_types: Optional[list[MessageType]] = None,
    ) -> None:
        """Register an agent with the message bus.

        Args:
            agent_id: Agent's unique ID
            handler: Message handler function
            subscribed_types: Message types to subscribe to

        """
        async with self._lock:
            self._message_handlers[agent_id] = handler

            # Subscribe to message types
            if subscribed_types:
                for msg_type in subscribed_types:
                    self._subscribers[msg_type].add(agent_id)
            else:
                # Subscribe to all types by default
                for msg_type in MessageType:
                    self._subscribers[msg_type].add(agent_id)

            logger.info(
                "Agent registered with message bus",
                agent_id=str(agent_id),
                subscribed_types=[t.value for t in subscribed_types] if subscribed_types else "all",
            )

    async def unregister_agent(self, agent_id: UUID) -> None:
        """Unregister an agent from the message bus.

        Args:
            agent_id: Agent's unique ID

        """
        async with self._lock:
            # Remove from handlers
            self._message_handlers.pop(agent_id, None)

            # Remove from all subscriptions
            for subscribers in self._subscribers.values():
                subscribers.discard(agent_id)

            # Clear message queue
            self._message_queue.pop(agent_id, None)

            logger.info("Agent unregistered from message bus", agent_id=str(agent_id))

    async def send_message(self, message: Message) -> None:
        """Send a message through the bus.

        Args:
            message: Message to send

        """
        if message.receiver_id:
            # Direct message
            await self._deliver_direct_message(message)
        else:
            # Broadcast message
            await self._broadcast_message(message)

    async def _deliver_direct_message(self, message: Message) -> None:
        """Deliver a message to a specific agent.

        Args:
            message: Message to deliver

        """
        async with self._lock:
            if message.receiver_id not in self._message_handlers:
                logger.warning(
                    "Receiver not found for message",
                    receiver_id=str(message.receiver_id),
                    message_type=message.message_type.value,
                )
                return

            # Add to queue
            self._message_queue[message.receiver_id].append(message)

        # Process outside lock to avoid deadlock
        await self._process_agent_queue(message.receiver_id)

    async def _broadcast_message(self, message: Message) -> None:
        """Broadcast a message to all subscribed agents.

        Args:
            message: Message to broadcast

        """
        async with self._lock:
            # Add to broadcast history
            self._broadcast_history.append(message)

            # Get subscribers for this message type
            subscribers = self._subscribers.get(message.message_type, set()).copy()

            # Queue for all subscribers
            for agent_id in subscribers:
                if agent_id != message.sender_id:  # Don't send to self
                    self._message_queue[agent_id].append(message)

        # Process queues outside lock
        await asyncio.gather(
            *[self._process_agent_queue(agent_id) for agent_id in subscribers],
            return_exceptions=True,
        )

    async def _process_agent_queue(self, agent_id: UUID) -> None:
        """Process messages in an agent's queue.

        Args:
            agent_id: Agent ID

        """
        while True:
            message = None
            handler = None

            async with self._lock:
                if agent_id in self._message_queue and self._message_queue[agent_id]:
                    message = self._message_queue[agent_id].popleft()
                    handler = self._message_handlers.get(agent_id)

            if not message or not handler:
                break

            try:
                # Call handler
                await handler(message)

                logger.debug(
                    "Message delivered",
                    agent_id=str(agent_id),
                    message_id=str(message.id),
                    message_type=message.message_type.value,
                )
            except Exception as e:
                logger.error(
                    "Message handler error",
                    agent_id=str(agent_id),
                    message_id=str(message.id),
                    error=str(e),
                    exc_info=True,
                )

    async def get_pending_messages(self, agent_id: UUID) -> list[Message]:
        """Get pending messages for an agent.

        Args:
            agent_id: Agent ID

        Returns:
            List of pending messages

        """
        async with self._lock:
            return list(self._message_queue.get(agent_id, []))

    async def get_broadcast_history(
        self, message_type: Optional[MessageType] = None, limit: int = 50
    ) -> list[Message]:
        """Get broadcast message history.

        Args:
            message_type: Filter by message type
            limit: Maximum messages to return

        Returns:
            List of broadcast messages

        """
        async with self._lock:
            messages = list(self._broadcast_history)

            if message_type:
                messages = [m for m in messages if m.message_type == message_type]

            return messages[-limit:]


class SharedContext:
    """Manages shared context between agents."""

    def __init__(self):
        """Initialize shared context."""
        self._data: dict[str, Any] = {}
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._subscribers: dict[str, set[UUID]] = defaultdict(set)
        self._change_handlers: dict[UUID, Callable] = {}

    async def set(self, key: str, value: Any, agent_id: UUID) -> None:
        """Set a value in shared context.

        Args:
            key: Context key
            value: Value to set
            agent_id: ID of agent setting the value

        """
        async with self._locks[key]:
            old_value = self._data.get(key)
            self._data[key] = value

            logger.debug(
                "Shared context updated",
                key=key,
                agent_id=str(agent_id),
                has_old_value=old_value is not None,
            )

        # Notify subscribers
        await self._notify_change(key, old_value, value, agent_id)

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from shared context.

        Args:
            key: Context key

        Returns:
            Value or None

        """
        async with self._locks[key]:
            return self._data.get(key)

    async def update(self, key: str, updater: Callable[[Any], Any], agent_id: UUID) -> Any:
        """Update a value atomically.

        Args:
            key: Context key
            updater: Function to update the value
            agent_id: ID of agent updating

        Returns:
            Updated value

        """
        async with self._locks[key]:
            old_value = self._data.get(key)
            new_value = updater(old_value)
            self._data[key] = new_value

        await self._notify_change(key, old_value, new_value, agent_id)
        return new_value

    async def subscribe(
        self, key: str, agent_id: UUID, handler: Callable[[str, Any, Any], Any]
    ) -> None:
        """Subscribe to changes for a key.

        Args:
            key: Context key to watch
            agent_id: Subscribing agent ID
            handler: Change handler function(key, old_value, new_value)

        """
        self._subscribers[key].add(agent_id)
        self._change_handlers[agent_id] = handler

        logger.debug(
            "Agent subscribed to context key",
            key=key,
            agent_id=str(agent_id),
        )

    async def unsubscribe(self, key: str, agent_id: UUID) -> None:
        """Unsubscribe from changes.

        Args:
            key: Context key
            agent_id: Agent ID

        """
        self._subscribers[key].discard(agent_id)
        self._change_handlers.pop(agent_id, None)

    async def _notify_change(
        self, key: str, old_value: Any, new_value: Any, updater_id: UUID
    ) -> None:
        """Notify subscribers of a change.

        Args:
            key: Changed key
            old_value: Previous value
            new_value: New value
            updater_id: ID of agent that made the change

        """
        subscribers = self._subscribers.get(key, set()).copy()

        # Notify all subscribers except the updater
        notify_tasks = []
        for agent_id in subscribers:
            if agent_id != updater_id and agent_id in self._change_handlers:
                handler = self._change_handlers[agent_id]
                notify_tasks.append(handler(key, old_value, new_value))

        if notify_tasks:
            await asyncio.gather(*notify_tasks, return_exceptions=True)

    async def get_all(self) -> dict[str, Any]:
        """Get all shared context data.

        Returns:
            Copy of all context data

        """
        # No lock needed for read-only operation on dict
        return self._data.copy()


class CommunicationHub:
    """Central hub managing all communication components."""

    def __init__(self):
        """Initialize communication hub."""
        self.message_bus = MessageBus()
        self.shared_context = SharedContext()
        self._event_handlers: dict[str, list[Callable]] = defaultdict(list)
        self._agent_metadata: dict[UUID, dict[str, Any]] = {}

        logger.info("Communication hub initialized")

    async def register_agent(self, agent: Agent, metadata: Optional[dict[str, Any]] = None) -> None:
        """Register an agent with the communication system.

        Args:
            agent: Agent to register
            metadata: Optional agent metadata

        """
        # Store metadata
        self._agent_metadata[agent.id] = metadata or {
            "role": agent.role.value,
            "status": agent.status,
            "registered_at": datetime.utcnow(),
        }

        # Create message handler wrapper
        async def message_handler(message: Message) -> dict[str, Any]:
            """Handle incoming messages for the agent."""
            try:
                response = await agent.collaborate(
                    self, message.to_dict()  # Pass hub as "other_agent" for context
                )

                # Send response if required
                if message.requires_response and response:
                    response_msg = Message(
                        sender_id=agent.id,
                        receiver_id=message.sender_id,
                        message_type=MessageType.TASK_RESPONSE,
                        subject=f"Re: {message.subject}",
                        content=response,
                        correlation_id=message.id,
                    )
                    await self.message_bus.send_message(response_msg)

                return response

            except Exception as e:
                logger.error(
                    "Agent message handling error",
                    agent_id=str(agent.id),
                    message_id=str(message.id),
                    error=str(e),
                    exc_info=True,
                )
                raise

        # Register with message bus
        await self.message_bus.register_agent(agent.id, message_handler)

        # Emit registration event
        await self.emit_event(
            "agent_registered",
            {
                "agent_id": str(agent.id),
                "role": agent.role.value,
                "metadata": metadata,
            },
        )

        logger.info(
            "Agent registered with communication hub",
            agent_id=str(agent.id),
            role=agent.role.value,
        )

    async def unregister_agent(self, agent_id: UUID) -> None:
        """Unregister an agent from the communication system.

        Args:
            agent_id: Agent ID to unregister

        """
        # Remove from message bus
        await self.message_bus.unregister_agent(agent_id)

        # Remove metadata
        self._agent_metadata.pop(agent_id, None)

        # Emit event
        await self.emit_event(
            "agent_unregistered",
            {
                "agent_id": str(agent_id),
            },
        )

        logger.info("Agent unregistered from communication hub", agent_id=str(agent_id))

    async def send_message(
        self,
        sender_id: UUID,
        receiver_id: Optional[UUID],
        message_type: MessageType,
        content: dict[str, Any],
        priority: MessagePriority = MessagePriority.NORMAL,
        requires_response: bool = False,
    ) -> Message:
        """Send a message between agents.

        Args:
            sender_id: Sender agent ID
            receiver_id: Receiver agent ID (None for broadcast)
            message_type: Type of message
            content: Message content
            priority: Message priority
            requires_response: Whether response is required

        Returns:
            Sent message

        """
        message = Message(
            sender_id=sender_id,
            receiver_id=receiver_id,
            message_type=message_type,
            priority=priority,
            content=content,
            requires_response=requires_response,
        )

        await self.message_bus.send_message(message)

        return message

    async def broadcast(
        self, sender_id: UUID, message_type: MessageType, subject: str, content: dict[str, Any]
    ) -> Message:
        """Broadcast a message to all agents.

        Args:
            sender_id: Sender agent ID
            message_type: Type of message
            subject: Message subject
            content: Message content

        Returns:
            Broadcast message

        """
        message = Message(
            sender_id=sender_id,
            receiver_id=None,
            message_type=message_type,
            subject=subject,
            content=content,
            priority=MessagePriority.NORMAL,
        )

        await self.message_bus.send_message(message)

        logger.info(
            "Broadcast message sent",
            sender_id=str(sender_id),
            message_type=message_type.value,
            subject=subject,
        )

        return message

    def subscribe_to_event(self, event_name: str, handler: Callable) -> None:
        """Subscribe to system events.

        Args:
            event_name: Event to subscribe to
            handler: Event handler function

        """
        self._event_handlers[event_name].append(handler)

    async def emit_event(self, event_name: str, data: dict[str, Any]) -> None:
        """Emit a system event.

        Args:
            event_name: Event name
            data: Event data

        """
        handlers = self._event_handlers.get(event_name, [])

        if handlers:
            await asyncio.gather(*[handler(data) for handler in handlers], return_exceptions=True)

    def get_agent_metadata(self, agent_id: UUID) -> Optional[dict[str, Any]]:
        """Get metadata for an agent.

        Args:
            agent_id: Agent ID

        Returns:
            Agent metadata or None

        """
        return self._agent_metadata.get(agent_id)

    def get_all_agents(self) -> dict[UUID, dict[str, Any]]:
        """Get all registered agents and their metadata.

        Returns:
            Dictionary of agent IDs to metadata

        """
        return self._agent_metadata.copy()
