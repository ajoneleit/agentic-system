"""Core interfaces and abstract base classes for the Agentic Coding System.

This module defines the fundamental abstractions that all components must implement,
ensuring consistency and extensibility throughout the system.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TypeVar, Generic
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


T = TypeVar("T")


class TaskStatus(str, Enum):
    """Status of a task in the system."""
    
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """Priority levels for task execution."""
    
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentRole(str, Enum):
    """Specialized roles for sub-agents."""
    
    CORE_LOGIC = "core_logic"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    OPTIMIZATION = "optimization"
    VERIFICATION = "verification"
    META = "meta"


class ArtifactType(str, Enum):
    """Types of artifacts produced by agents."""
    
    SOURCE_CODE = "source_code"
    TEST_CODE = "test_code"
    DOCUMENTATION = "documentation"
    CONFIGURATION = "configuration"
    SCHEMA = "schema"
    BUILD_OUTPUT = "build_output"


@dataclass
class TaskContext:
    """Context information for task execution.
    
    Provides agents with necessary information about the current
    execution environment and related tasks.
    """
    
    project_root: Path
    shared_memory: Dict[str, Any] = field(default_factory=dict)
    parent_task_id: Optional[UUID] = None
    sibling_task_ids: Set[UUID] = field(default_factory=set)
    global_constraints: Dict[str, Any] = field(default_factory=dict)
    execution_metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Artifact management integration
    artifact_manager: Optional[Any] = None  # Will be ArtifactManager instance
    project_id: Optional[str] = None
    artifact_metadata_template: Dict[str, Any] = field(default_factory=dict)
    artifact_naming_convention: str = "{task_name}_{agent_type}_{timestamp}"
    enable_artifact_caching: bool = True
    auto_version_on_change: bool = True
    link_test_artifacts: bool = True


class Task(BaseModel):
    """Represents a unit of work in the system.
    
    Tasks are the fundamental work units that agents execute. They can have
    dependencies, produce artifacts, and be composed into larger workflows.
    """
    
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    
    # Task relationships
    dependencies: List[UUID] = Field(default_factory=list)
    subtasks: List[UUID] = Field(default_factory=list)
    parent_id: Optional[UUID] = None
    
    # Execution details
    assigned_agent_id: Optional[UUID] = None
    required_role: Optional[AgentRole] = None
    estimated_complexity: str = Field(default="medium")  # simple, medium, complex
    
    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    deadline: Optional[datetime] = None
    
    # Results
    artifacts: List[UUID] = Field(default_factory=list)
    error_message: Optional[str] = None
    verification_results: Dict[str, Any] = Field(default_factory=dict)
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tags: Set[str] = Field(default_factory=set)
    
    def is_ready(self, completed_tasks: Set[UUID]) -> bool:
        """Check if task is ready to execute based on dependencies.
        
        Args:
            completed_tasks: Set of completed task IDs
            
        Returns:
            True if all dependencies are satisfied
        """
        return all(dep_id in completed_tasks for dep_id in self.dependencies)
    
    def mark_started(self) -> None:
        """Mark task as started."""
        self.status = TaskStatus.IN_PROGRESS
        self.started_at = datetime.now(timezone.utc)
    
    def mark_completed(self) -> None:
        """Mark task as completed."""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
    
    def mark_failed(self, error: str) -> None:
        """Mark task as failed with error message."""
        self.status = TaskStatus.FAILED
        self.error_message = error
        self.completed_at = datetime.now(timezone.utc)


class Artifact(BaseModel):
    """Represents a code artifact produced by an agent.
    
    Artifacts are versioned outputs from agents, including source code,
    tests, documentation, and other deliverables.
    """
    
    id: UUID = Field(default_factory=uuid4)
    type: ArtifactType
    name: str
    path: Path
    
    # Versioning
    version: int = Field(default=1)
    previous_version_id: Optional[UUID] = None
    
    # Content
    content: str
    language: Optional[str] = None
    encoding: str = Field(default="utf-8")
    size_bytes: int = Field(default=0)
    checksum: Optional[str] = None
    
    # Metadata
    task_id: UUID
    agent_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    modified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Relationships
    dependencies: List[UUID] = Field(default_factory=list)
    dependent_artifacts: List[UUID] = Field(default_factory=list)
    
    # Validation
    compilation_status: Optional[bool] = None
    test_coverage: Optional[float] = None
    quality_score: Optional[float] = None
    
    # Additional metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tags: Set[str] = Field(default_factory=set)
    
    def increment_version(self) -> "Artifact":
        """Create a new version of this artifact.
        
        Returns:
            New artifact instance with incremented version
        """
        return Artifact(
            type=self.type,
            name=self.name,
            path=self.path,
            version=self.version + 1,
            previous_version_id=self.id,
            content=self.content,
            language=self.language,
            task_id=self.task_id,
            agent_id=self.agent_id,
            dependencies=self.dependencies.copy(),
            metadata=self.metadata.copy(),
            tags=self.tags.copy(),
        )


class PromptTemplate(BaseModel):
    """Template for generating prompts with variable substitution.
    
    Supports versioning and performance tracking to enable
    continuous improvement of prompts.
    """
    
    id: UUID = Field(default_factory=uuid4)
    name: str
    template: str
    version: int = Field(default=1)
    
    # Performance metrics
    usage_count: int = Field(default=0)
    success_rate: float = Field(default=0.0)
    average_completion_time: float = Field(default=0.0)
    
    # Evolution
    parent_template_id: Optional[UUID] = None
    improvement_notes: Optional[str] = None
    
    # Metadata
    variables: List[str] = Field(default_factory=list)
    tags: Set[str] = Field(default_factory=set)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    def render(self, **kwargs: Any) -> str:
        """Render template with provided variables.
        
        Args:
            **kwargs: Variable substitutions
            
        Returns:
            Rendered prompt string
        """
        return self.template.format(**kwargs)
    
    def track_usage(self, success: bool, duration: float) -> None:
        """Track usage metrics for continuous improvement.
        
        Args:
            success: Whether the prompt led to successful task completion
            duration: Time taken to complete the task
        """
        self.usage_count += 1
        # Update success rate with running average
        self.success_rate = (
            (self.success_rate * (self.usage_count - 1) + float(success))
            / self.usage_count
        )
        # Update average completion time
        self.average_completion_time = (
            (self.average_completion_time * (self.usage_count - 1) + duration)
            / self.usage_count
        )


class Agent(ABC):
    """Abstract base class for all agents in the system.
    
    Defines the interface that all agents (meta and sub-agents) must implement.
    Supports async operations for efficient parallel execution.
    """
    
    def __init__(self, agent_id: UUID, role: AgentRole):
        """Initialize agent with unique ID and role.
        
        Args:
            agent_id: Unique identifier for this agent
            role: Specialized role of this agent
        """
        self.id = agent_id
        self.role = role
        self.status = "idle"
        self.current_task: Optional[Task] = None
        self.completed_tasks: List[UUID] = []
        self.produced_artifacts: List[UUID] = []
    
    @abstractmethod
    async def initialize(self, context: TaskContext) -> None:
        """Initialize agent with execution context.
        
        Args:
            context: Task execution context
        """
        pass
    
    @abstractmethod
    async def execute_task(self, task: Task, context: TaskContext) -> "TaskResult":
        """Execute a task and produce artifacts.
        
        Args:
            task: Task to execute
            context: Execution context
            
        Returns:
            TaskResult with produced artifacts and execution details
        """
        pass
    
    @abstractmethod
    async def collaborate(self, other_agent: "Agent", message: Dict[str, Any]) -> Dict[str, Any]:
        """Collaborate with another agent.
        
        Args:
            other_agent: Agent to collaborate with
            message: Communication message
            
        Returns:
            Response message
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Gracefully shutdown the agent."""
        pass
    
    async def report_status(self) -> Dict[str, Any]:
        """Report current agent status.
        
        Returns:
            Status information dictionary
        """
        return {
            "id": str(self.id),
            "role": self.role.value,
            "status": self.status,
            "current_task": str(self.current_task.id) if self.current_task else None,
            "completed_tasks": len(self.completed_tasks),
            "produced_artifacts": len(self.produced_artifacts),
        }


class Verifier(ABC):
    """Abstract base class for verification components.
    
    Verifiers ensure that artifacts meet quality standards through
    compilation checks, test execution, and other validation methods.
    """
    
    @abstractmethod
    async def verify(self, artifact: Artifact) -> Dict[str, Any]:
        """Verify an artifact meets quality standards.
        
        Args:
            artifact: Artifact to verify
            
        Returns:
            Verification results dictionary with at least:
                - success: bool
                - errors: List[str]
                - warnings: List[str]
                - metrics: Dict[str, Any]
        """
        pass
    
    @abstractmethod
    async def verify_batch(self, artifacts: List[Artifact]) -> Dict[UUID, Dict[str, Any]]:
        """Verify multiple artifacts efficiently.
        
        Args:
            artifacts: List of artifacts to verify
            
        Returns:
            Dictionary mapping artifact IDs to verification results
        """
        pass
    
    @abstractmethod
    def supports_artifact_type(self, artifact_type: ArtifactType) -> bool:
        """Check if verifier supports the given artifact type.
        
        Args:
            artifact_type: Type of artifact
            
        Returns:
            True if artifact type is supported
        """
        pass


class LearningEngine(ABC):
    """Abstract base class for the learning system.
    
    The learning engine analyzes patterns in task execution, identifies
    improvements, and evolves prompts and strategies over time.
    """
    
    @abstractmethod
    async def record_execution(
        self,
        task: Task,
        prompt_used: PromptTemplate,
        execution_time: float,
        success: bool,
        artifacts: List[Artifact],
    ) -> None:
        """Record task execution for learning.
        
        Args:
            task: Executed task
            prompt_used: Prompt template used
            execution_time: Time taken to complete
            success: Whether execution was successful
            artifacts: Produced artifacts
        """
        pass
    
    @abstractmethod
    async def analyze_patterns(self) -> Dict[str, Any]:
        """Analyze execution patterns to identify improvements.
        
        Returns:
            Analysis results with patterns and recommendations
        """
        pass
    
    @abstractmethod
    async def evolve_prompt(self, template: PromptTemplate) -> Optional[PromptTemplate]:
        """Evolve a prompt template based on performance data.
        
        Args:
            template: Current prompt template
            
        Returns:
            Improved template or None if no improvement found
        """
        pass
    
    @abstractmethod
    async def get_recommendations(self, task: Task) -> Dict[str, Any]:
        """Get recommendations for task execution.
        
        Args:
            task: Task to get recommendations for
            
        Returns:
            Recommendations dictionary with strategies and parameters
        """
        pass


class ArtifactManager(ABC):
    """Abstract base class for artifact storage and retrieval.
    
    Manages versioning, dependencies, and efficient storage of all
    artifacts produced by the system.
    """
    
    @abstractmethod
    async def store(self, artifact: Artifact) -> UUID:
        """Store an artifact and return its ID.
        
        Args:
            artifact: Artifact to store
            
        Returns:
            Stored artifact ID
        """
        pass
    
    @abstractmethod
    async def retrieve(self, artifact_id: UUID) -> Optional[Artifact]:
        """Retrieve an artifact by ID.
        
        Args:
            artifact_id: ID of artifact to retrieve
            
        Returns:
            Artifact or None if not found
        """
        pass
    
    @abstractmethod
    async def list_versions(self, name: str, artifact_type: ArtifactType) -> List[Artifact]:
        """List all versions of an artifact.
        
        Args:
            name: Artifact name
            artifact_type: Type of artifact
            
        Returns:
            List of artifact versions, newest first
        """
        pass
    
    @abstractmethod
    async def resolve_dependencies(self, artifact_id: UUID) -> List[Artifact]:
        """Resolve all dependencies for an artifact.
        
        Args:
            artifact_id: ID of artifact
            
        Returns:
            List of dependency artifacts in order
        """
        pass
    
    @abstractmethod
    async def cleanup_old_versions(self, keep_count: int = 10) -> int:
        """Clean up old artifact versions.
        
        Args:
            keep_count: Number of versions to keep per artifact
            
        Returns:
            Number of artifacts cleaned up
        """
        pass


class MetaAgentInterface(ABC):
    """Abstract base class for the meta agent (orchestrator).
    
    IMPORTANT: MetaAgent does NOT inherit from Agent because it has fundamentally
    different responsibilities. While Agents execute specific tasks, the MetaAgent
    orchestrates the entire system:
    
    - Agents: Execute tasks, produce artifacts, collaborate with peers
    - MetaAgent: Decomposes requests, spawns agents, coordinates execution
    
    This separation follows the principle of composition over inheritance.
    The MetaAgent *uses* Agents but is not itself an Agent.
    """
    
    def __init__(self):
        """Initialize the meta agent orchestrator."""
        self.id = uuid4()
        self.role = AgentRole.META
        self.active_agents: Dict[UUID, Agent] = {}
        self.is_initialized = False
    
    @abstractmethod
    async def initialize(self, context: TaskContext) -> None:
        """Initialize the meta agent with system context.
        
        Args:
            context: System-wide execution context
        """
        pass
    
    @abstractmethod
    async def process_request(self, user_request: str) -> "ProjectResult":
        """Process a complete user request from start to finish.
        
        This is the main entry point for the MetaAgent. It handles the entire
        lifecycle of a user request including decomposition, execution, and
        result aggregation.
        
        Args:
            user_request: The user's coding request in natural language
            
        Returns:
            ProjectResult with all artifacts and execution metrics
        """
        pass
    
    @abstractmethod
    async def decompose_task(self, user_prompt: str) -> List[Task]:
        """Decompose user prompt into executable tasks.
        
        Uses Claude to analyze the request and break it down into specific,
        actionable tasks with proper dependencies.
        
        Args:
            user_prompt: User's request in natural language
            
        Returns:
            List of decomposed tasks with dependencies
        """
        pass
    
    @abstractmethod
    async def spawn_agent(self, role: AgentRole) -> Agent:
        """Spawn a new sub-agent with specified role.
        
        Creates and initializes a new agent instance based on the role.
        
        Args:
            role: Role for the new agent
            
        Returns:
            Newly created and initialized agent instance
        """
        pass
    
    @abstractmethod
    async def coordinate_execution(self, tasks: List[Task]) -> Dict[UUID, List[Artifact]]:
        """Coordinate the execution of tasks by managing agents.
        
        This method handles the core orchestration logic including:
        - Agent lifecycle management
        - Task assignment based on agent capabilities
        - Parallel execution where possible
        - Result collection
        
        Args:
            tasks: List of tasks to execute
            
        Returns:
            Dictionary mapping task IDs to produced artifacts
        """
        pass
    
    @abstractmethod
    async def monitor_progress(self) -> Dict[str, Any]:
        """Monitor overall system progress.
        
        Provides real-time insights into:
        - Task completion status
        - Agent utilization
        - System performance metrics
        - Potential bottlenecks
        
        Returns:
            Comprehensive progress report
        """
        pass
    
    @abstractmethod
    async def handle_failure(self, task: Task, error: str) -> List[Task]:
        """Handle task failure and generate repair tasks.
        
        When a task fails, this method:
        - Analyzes the failure
        - Determines if it can be automatically fixed
        - Generates repair tasks if possible
        - Updates task dependencies
        
        Args:
            task: Failed task
            error: Error message/details
            
        Returns:
            List of repair tasks to fix the issue
        """
        pass
    
    @abstractmethod
    async def aggregate_results(self, task_results: Dict[UUID, List[Artifact]]) -> "ProjectResult":
        """Aggregate all task results into a final project result.
        
        Combines all artifacts and metrics into a cohesive result that
        can be presented to the user.
        
        Args:
            task_results: Dictionary mapping task IDs to artifacts
            
        Returns:
            Aggregated project result
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Gracefully shutdown the meta agent and all sub-agents.
        
        Ensures proper cleanup of all resources including:
        - Terminating all active agents
        - Closing connections
        - Saving any pending state
        """
        pass
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get current system status.
        
        Returns:
            System status including agent states and resource usage
        """
        return {
            "id": str(self.id),
            "role": self.role.value,
            "active_agents": len(self.active_agents),
            "is_initialized": self.is_initialized,
            "agents": [
                await agent.report_status() 
                for agent in self.active_agents.values()
            ]
        }