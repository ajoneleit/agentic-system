"""Meta Agent implementation for the Agentic Coding System.

The Meta Agent orchestrates the entire system, decomposing user requests into
tasks, spawning sub-agents, and coordinating their activities.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from uuid import UUID, uuid4

from structlog import get_logger

from config import get_settings
from src.agents.sub_agent import (
    CodeGeneratorAgent,
    DebugAgent,
    DocumentationAgent,
    RefactorAgent,
    TestWriterAgent,
)
from src.core.artifact_manager import ArtifactManager
from src.core.communication import CommunicationHub, MessageType
from src.core.coordinator import AgentCoordinator
from src.core.dependency_tracker import DependencyTracker
from src.core.exceptions import (
    TaskError,
)
from src.core.result import Result, AsyncResult, collect_results, aggregate_errors
from src.core.agent_errors import (
    MetaAgentError,
    TaskDecompositionError as TaskDecompError,
    AgentSpawnError,
    OrchestrationError,
    ResultAggregationError,
)
from src.core.interfaces import (
    Agent,
    AgentRole,
    Artifact,
    ArtifactType,
    MetaAgentInterface,
    Task,
    TaskContext,
    TaskPriority,
    TaskStatus,
)
from src.core.task_manager import TaskManager
from src.core.task_result import ExecutionResult, TaskResult
from src.core.failure_analyzer import FailureAnalyzer, ErrorDiagnosis, RetryStrategy
from src.prompts.task_decomposition import (
    get_decomposition_prompt,
    TASK_ANALYSIS_PROMPT,
    DEPENDENCY_ANALYSIS_PROMPT,
    PROGRESS_AGGREGATION_PROMPT,
)
from src.utils.app_logging import log_execution_time

# TEMP: Backward compatibility shim for test compatibility
try:
    from src.clients.claude_client import ClaudeClient as _ClaudeClient
    ClaudeClient = _ClaudeClient  # TEMP shim for test compatibility
except ImportError:
    ClaudeClient = None  # Fallback if module doesn't exist

logger = get_logger(__name__)


# Helper function for async/sync compatibility
import inspect

async def _await_if_needed(obj):
    """Handle both async and sync objects for test compatibility"""
    return await obj if inspect.isawaitable(obj) else obj


@dataclass
class ProjectResult:
    """Result of processing a user request."""
    
    project_name: str = ""
    success: bool = True
    artifacts: List[Artifact] = field(default_factory=list)
    execution_time: float = 0.0
    tasks_completed: int = 0
    tasks_failed: int = 0
    success_rate: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    tasks: List[Task] = field(default_factory=list)
    retry_summary: Dict[UUID, int] = field(default_factory=dict)  # task_id -> retry_count
    failure_reports: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def successful_tasks(self) -> int:
        """Get number of successful tasks."""
        return self.tasks_completed
    
    @property
    def failed_tasks(self) -> int:
        """Get number of failed tasks."""
        return self.tasks_failed


class MetaAgent(MetaAgentInterface):
    """Meta Agent that orchestrates the entire coding system.
    
    The MetaAgent is the central orchestrator that:
    - Decomposes user requests into tasks
    - Spawns and manages sub-agents
    - Coordinates task execution
    - Handles failures and recovery
    - Aggregates results
    
    It does NOT execute tasks directly - that's the job of sub-agents.
    """
    
    def __init__(self, artifact_storage_path: Optional[Path] = None):
        """Initialize Meta Agent.
        
        Args:
            artifact_storage_path: Path for artifact storage (defaults to ./projects)
        """
        super().__init__()  # MetaAgentInterface handles id and role
        
        # Initialize components
        settings = get_settings()
        
        # Meta Agent ALWAYS uses OpenAI O3
        from src.clients.openai_client import OpenAIClient
        self.ai_client = OpenAIClient()
        self.using_openai = True  # MetaAgent always uses OpenAI O3
        logger.info(
            "MetaAgent using OpenAI O3 for task decomposition",
            model=settings.openai.meta_agent_model if settings.openai else "o3"
        )
        
        self.task_manager = TaskManager()
        self.communication_hub = CommunicationHub()
        self.coordinator = AgentCoordinator(
            self.task_manager,
            self.communication_hub
        )
        
        # Initialize artifact management
        self.artifact_storage_path = artifact_storage_path or Path("./projects")
        self.artifact_manager = ArtifactManager(
            storage_path=self.artifact_storage_path,
            max_memory_cache_size=100,
            enable_compression=True,
            auto_cleanup_days=30
        )
        self.dependency_tracker = DependencyTracker()
        
        # Initialize retry and failure analysis
        settings = get_settings()
        self.max_retries = settings.agent.task_max_retries
        self.retry_delay = settings.agent.task_retry_delay
        self.retry_backoff = settings.agent.task_retry_backoff
        self.retry_on_verification_failure = settings.agent.retry_on_verification_failure
        self.retry_on_api_errors = settings.agent.retry_on_api_errors
        self.diagnose_failures = settings.agent.diagnose_failures
        self.failure_analyzer = FailureAnalyzer()
        
        # Task retry tracking
        self._task_retry_counts: Dict[UUID, int] = {}
        self._task_retry_history: Dict[UUID, List[Dict[str, Any]]] = {}
        
        # Register agent factories
        self._register_agent_factories()
        
        # Internal state
        self._active_project: Optional[Dict[str, Any]] = None
        self._project_artifacts: List[Artifact] = []
        self._current_project_id: Optional[str] = None
        self._start_time: Optional[datetime] = None
        self._task_results: Dict[UUID, TaskResult] = {}  # Track task execution results
        self.context: Optional[TaskContext] = None  # Will be set via initialize() or manually
        self._project_path: Path = self.artifact_storage_path / "default_project"  # Default project path
        self._workspace_path: Path = self._project_path / "workspace"  # Default workspace path
        
        logger.info("MetaAgent initialized with retry support", 
                   max_retries=self.max_retries,
                   retry_delay=self.retry_delay)
    
    def _register_agent_factories(self) -> None:
        """Register factories for creating sub-agents."""
        self.coordinator.register_agent_factory(
            AgentRole.CORE_LOGIC,
            CodeGeneratorAgent
        )
        self.coordinator.register_agent_factory(
            AgentRole.TESTING,
            TestWriterAgent
        )
        self.coordinator.register_agent_factory(
            AgentRole.DOCUMENTATION,
            DocumentationAgent
        )
        self.coordinator.register_agent_factory(
            AgentRole.OPTIMIZATION,
            RefactorAgent
        )
        self.coordinator.register_agent_factory(
            AgentRole.VERIFICATION,
            DebugAgent
        )
    
    async def initialize(self, context: TaskContext) -> None:
        """Initialize Meta Agent with context.
        
        Args:
            context: Execution context
        """
        # Store context
        self.context = context
        self.is_initialized = True
        
        # Start coordinator
        await self.coordinator.start()
        
        # Register self with communication hub
        await self.communication_hub.register_agent(self, {
            "role": "orchestrator",
            "capabilities": ["task_decomposition", "agent_spawning", "coordination"]
        })
        
        logger.info("MetaAgent fully initialized")
    
    @log_execution_time("process_request")
    async def process_request(self, user_request: str) -> Result[ProjectResult]:
        """Process a user request end-to-end.
        
        Args:
            user_request: User's coding request
            
        Returns:
            Result containing project execution result or error
        """
        self._start_time = datetime.utcnow()
        logger.info("Processing user request", request_length=len(user_request))
        
        try:
            # 1. Initialize project storage
            project_id = await self._initialize_project_storage(user_request)
            self._current_project_id = project_id
            logger.info("Initialized project storage", project_id=project_id)
            
            # 2. Decompose the request into tasks
            decompose_result = await self.decompose_request(user_request)
            if decompose_result.is_failure():
                return Result.failure(decompose_result.get_error())
            
            tasks = decompose_result.unwrap()
            logger.info(f"Decomposed into {len(tasks)} tasks")
            
            # 3. Add tasks to task manager
            await self.task_manager.add_tasks(tasks)
            
            # 4. Create execution context with artifact manager
            context = TaskContext(
                project_root=self._project_path,  # Always use the specific project path
                shared_memory={
                    "project_summary": self._active_project.get("project_summary", "") if self._active_project else "",
                    "user_request": user_request,
                    "workspace_path": str(self._workspace_path),  # Central workspace for all files
                    "project_files": [],  # Will be populated as files are created
                },
                parent_task_id=None,
                sibling_task_ids=set(t.id for t in tasks),
                # Artifact management integration
                artifact_manager=self.artifact_manager,
                project_id=project_id,
                artifact_metadata_template={
                    "project_id": project_id,
                    "request": user_request[:200],  # First 200 chars
                    "created_by": "agentic_system",
                },
                artifact_naming_convention="{name}",
                enable_artifact_caching=True,
                auto_version_on_change=True,
                link_test_artifacts=True,
            )
            
            # 5. Execute tasks using the coordination method
            execution_result = await self.coordinate_execution(tasks, context)
            if execution_result.is_failure():
                return Result.failure(execution_result.get_error())
            
            task_results = execution_result.unwrap()
            
            # 6. Store execution artifacts
            await self._store_execution_artifacts(task_results)
            
            # 7. Create project manifest
            manifest = await self._create_project_manifest(user_request, task_results)
            
            # 8. Aggregate results
            aggregate_result = await self.aggregate_results(task_results)
            if aggregate_result.is_failure():
                return Result.failure(aggregate_result.get_error())
            
            result = aggregate_result.unwrap()
            
            logger.info(
                "Request processing complete",
                project_id=project_id,
                tasks_completed=result.tasks_completed,
                tasks_failed=result.tasks_failed,
                execution_time=result.execution_time,
            )
            
            return Result.success(result)
            
        except Exception as e:
            logger.error(
                "Failed to process request",
                error=str(e),
                exc_info=True,
            )
            return Result.failure(
                OrchestrationError(
                    message=f"Failed to process request: {str(e)}",
                    agent_id=self.id,
                    details={"user_request": user_request[:200]}
                )
            )
    
    async def decompose_request(self, user_prompt: str) -> Result[List[Task]]:
        """Decompose user prompt into executable tasks.
        
        Args:
            user_prompt: User's request
            
        Returns:
            Result containing list of decomposed tasks or error
        """
        try:
            tasks = await self.decompose_task(user_prompt)
            return Result.success(tasks)
        except TaskDecompError as e:
            return Result.failure(e)
        except Exception as e:
            return Result.failure(
                TaskDecompError(
                    message=f"Failed to decompose request: {str(e)}",
                    agent_id=self.id,
                    details={"user_prompt": user_prompt[:200]}
                )
            )
    
    async def decompose_task(self, user_prompt: str) -> List[Task]:
        """Decompose user prompt into executable tasks.
        
        Args:
            user_prompt: User's request
            
        Returns:
            List of decomposed tasks with dependencies
        """
        try:
            # Use AI client to analyze the request
            prompt = TASK_ANALYSIS_PROMPT.render(user_request=user_prompt)
            
            # Use OpenAI O3 for task decomposition
            response = await _await_if_needed(self.ai_client.create_message(
                messages=[{"role": "user", "content": prompt}],
                temperature=1.0,  # o3 only supports temperature=1
                max_tokens=4096,
            ))
            response_text = response["content"]
            
            # Parse the response
            if not response_text:
                raise ValueError("Empty response from AI client")
                
            response_text = response_text.strip()
            
            # Try to extract JSON from the response
            # First check if response contains markdown code blocks
            if '```json' in response_text:
                import re
                json_match = re.search(r'```json\s*\n(.*?)```', response_text, re.DOTALL)
                if json_match:
                    json_text = json_match.group(1).strip()
                else:
                    # Fallback: just remove markdown
                    json_text = response_text.replace('```json', '').replace('```', '').strip()
            else:
                json_text = response_text
            
            # Now parse the JSON
            try:
                analysis = json.loads(json_text)
            except (json.JSONDecodeError, TypeError) as e:
                # Handle both JSONDecodeError and TypeError (when json_text is not a string)
                logger.warning(
                    "Initial JSON parsing failed",
                    error_type=type(e).__name__,
                    error_msg=str(e),
                    json_text_type=type(json_text).__name__
                )
                # Try to find JSON in the response
                import re
                # Convert to string if it's not already
                json_text_str = str(json_text) if not isinstance(json_text, str) else json_text
                # Look for JSON object that starts with { and ends with }
                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', json_text_str, re.DOTALL)
                if json_match:
                    try:
                        analysis = json.loads(json_match.group())
                    except (json.JSONDecodeError, TypeError) as e2:
                        logger.error(
                            "Found JSON-like content but failed to parse",
                            json_content=json_match.group()[:500],
                            error_type=type(e2).__name__
                        )
                        raise ValueError("Invalid JSON structure in response")
                else:
                    logger.error(
                        "Failed to find valid JSON in AI response",
                        response_preview=json_text_str[:500],
                        response_length=len(json_text_str)
                    )
                    raise ValueError("No valid JSON found in response")
            
            self._active_project = analysis
            
            # Log the raw task analysis for debugging
            logger.info("=== RAW TASK ANALYSIS FROM AI ===")
            for i, task_def in enumerate(analysis.get("tasks", [])):
                logger.info(f"Task {i+1}: {task_def.get('name', 'Unknown')}")
                logger.info(f"  Dependencies declared: {task_def.get('dependencies', [])}")
                logger.info(f"  Agent type: {task_def.get('agent_type', 'Unknown')}")
            logger.info("=== END RAW TASK ANALYSIS ===")
            
            # Create Task objects
            tasks = []
            task_map = {}  # name -> Task mapping for dependencies
            
            for task_def in analysis["tasks"]:
                # Handle OpenAI response format
                complexity = task_def.get("estimated_complexity") or task_def.get("complexity", "moderate")
                agent_type = task_def.get("type") or task_def.get("agent_type", "core_logic")
                
                task = Task(
                    name=task_def["name"],
                    description=task_def["description"],
                    priority=self._get_priority(complexity),
                    estimated_complexity=complexity,
                    required_role=self._get_agent_role(agent_type),
                    metadata={
                        "specification": task_def,
                        "deliverable": task_def.get("deliverable", ""),
                        "requirements": task_def.get("requirements", {}),
                    }
                )
                tasks.append(task)
                task_map[task.name] = task
            
            # Set dependencies
            for task_def, task in zip(analysis["tasks"], tasks):
                dep_list = task_def.get("dependencies", [])
                if dep_list:
                    logger.debug(f"Task '{task.name}' declares dependencies: {dep_list}")
                for dep_name in dep_list:
                    # Try exact match first
                    if dep_name in task_map:
                        task.dependencies.append(task_map[dep_name].id)
                        logger.debug(f"  - Mapped dependency '{dep_name}' to ID {task_map[dep_name].id}")
                    else:
                        # Try case-insensitive match
                        found = False
                        for task_name, task_obj in task_map.items():
                            if task_name.lower() == dep_name.lower():
                                task.dependencies.append(task_obj.id)
                                logger.warning(
                                    f"  - Mapped dependency '{dep_name}' to '{task_name}' (case-insensitive match)"
                                )
                                found = True
                                break
                        
                        if not found:
                            logger.error(
                                f"Task '{task.name}' has unknown dependency '{dep_name}'. "
                                f"Available tasks: {list(task_map.keys())}"
                            )
            
            # Debug logging for dependency analysis
            logger.info("=== DEPENDENCY DEBUG INFO ===")
            logger.info(f"Total tasks created: {len(tasks)}")
            
            # Log task_map to see all available tasks
            logger.info("Task map (name -> id):")
            for name, task_obj in task_map.items():
                logger.info(f"  '{name}' -> {task_obj.id}")
            
            # Log each task with its dependencies
            logger.info("Task dependency details:")
            for task in tasks:
                dep_names = []
                for dep_id in task.dependencies:
                    # Find the dependency name by looking up the ID
                    for name, t in task_map.items():
                        if t.id == dep_id:
                            dep_names.append(name)
                            break
                
                logger.info(f"  Task: '{task.name}' (ID: {task.id})")
                logger.info(f"    Dependencies by ID: {[str(d) for d in task.dependencies]}")
                logger.info(f"    Dependencies by name: {dep_names}")
                logger.info(f"    Agent type: {task.required_role}")
            
            # Check specifically for testing tasks
            testing_tasks = [t for t in tasks if t.required_role == AgentRole.TESTING]
            logger.info(f"Found {len(testing_tasks)} testing task(s)")
            testing_tasks_without_deps = []
            for test_task in testing_tasks:
                logger.info(f"  Testing task '{test_task.name}' depends on {len(test_task.dependencies)} task(s)")
                if len(test_task.dependencies) == 0:
                    testing_tasks_without_deps.append(test_task.name)
            
            if testing_tasks_without_deps:
                logger.error(
                    f"CRITICAL: Testing tasks without dependencies: {testing_tasks_without_deps}. "
                    "This WILL cause 'No Python file found' errors! Testing tasks must depend on core logic tasks."
                )
                
                # AUTO-FIX: Add dependencies to core logic tasks
                core_logic_tasks = [t for t in tasks if t.required_role == AgentRole.CORE_LOGIC]
                if core_logic_tasks:
                    logger.warning("AUTO-FIX: Adding dependencies to testing tasks...")
                    for test_task in testing_tasks:
                        if len(test_task.dependencies) == 0:
                            # Add all core logic tasks as dependencies
                            for core_task in core_logic_tasks:
                                test_task.dependencies.append(core_task.id)
                                logger.info(
                                    f"  - Added dependency: '{test_task.name}' now depends on '{core_task.name}'"
                                )
            
            logger.info("=== END DEPENDENCY DEBUG INFO ===")
            
            # Analyze dependencies for optimization
            try:
                # Store original dependencies as backup
                original_deps = {}
                for task in tasks:
                    original_deps[task.id] = list(task.dependencies)
                
                # Try to optimize dependencies
                optimized_deps = await self._analyze_dependencies(tasks)
                
                # Validate that optimization didn't break things
                if not self._validate_dependencies(optimized_deps, tasks):
                    # Restore original dependencies
                    logger.warning("Dependency optimization failed validation, using original dependencies")
                    for task in tasks:
                        task.dependencies = original_deps[task.id]
                        
            except Exception as e:
                logger.warning(
                    "Dependency analysis failed, using original dependencies",
                    error=str(e)
                )
                # Continue with original dependencies if analysis fails
            
            return tasks
            
        except Exception as e:
            logger.error(
                "Task decomposition failed",
                error=str(e),
                exc_info=True,
            )
            raise TaskDecompError(
                message=f"Task decomposition failed: {str(e)}",
                agent_id=self.id,
                details={"user_prompt": user_prompt[:200], "error": str(e)}
            )
    
    async def _analyze_dependencies(self, tasks: List[Task]) -> Optional[Dict[str, List[str]]]:
        """Analyze and optimize task dependencies.
        
        Args:
            tasks: List of tasks to analyze
            
        Returns:
            Dictionary mapping task IDs to their dependencies, or None if analysis fails
        """
        # Convert tasks to JSON for analysis
        tasks_json = json.dumps([
            {
                "id": str(t.id),
                "name": t.name,
                "dependencies": [str(d) for d in t.dependencies],
                "complexity": t.estimated_complexity,
            }
            for t in tasks
        ], indent=2)
        
        prompt = DEPENDENCY_ANALYSIS_PROMPT.render(tasks_json=tasks_json)
        
        # Use OpenAI O3 for dependency analysis
        response = await _await_if_needed(self.ai_client.create_message(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2048,
        ))
        
        # Parse and apply optimizations
        try:
            # Handle OpenAI response format
            response_text = response.get("content", "").strip()
            logger.debug(f"Raw dependency analysis response: {response_text[:200]}...")
            
            # Try to extract JSON if there's extra text
            # First, strip markdown code blocks if present
            if '```json' in response_text:
                # Extract content between ```json and ```
                import re
                json_match = re.search(r'```json\s*\n(.*?)\n```', response_text, re.DOTALL)
                if json_match:
                    json_text = json_match.group(1).strip()
                else:
                    # Fallback: just remove ```json and ```
                    json_text = response_text.replace('```json', '').replace('```', '').strip()
            elif response_text.startswith('{'):
                json_text = response_text
            else:
                # Look for the first { and extract from there
                json_start = response_text.find('{')
                if json_start != -1:
                    json_text = response_text[json_start:]
                else:
                    json_text = response_text
            
            analysis = json.loads(json_text)
            # Store analysis for later use
            if self._active_project:
                self._active_project["dependency_analysis"] = analysis
            
            # Extract dependencies based on the expected format
            dependencies = {}
            
            # Check for dependency_graph with task names
            if "dependency_graph" in analysis:
                # Map task names to IDs
                name_to_id = {task.name: str(task.id) for task in tasks}
                for task_name, task_info in analysis["dependency_graph"].items():
                    if task_name in name_to_id:
                        task_id = name_to_id[task_name]
                        deps_names = task_info.get("depends_on", [])
                        # Convert dependency names to IDs
                        dep_ids = []
                        for dep_name in deps_names:
                            if dep_name in name_to_id:
                                dep_id = name_to_id[dep_name]
                                # Prevent self-dependencies
                                if dep_id != task_id:
                                    dep_ids.append(dep_id)
                        dependencies[task_id] = dep_ids
            # Check for task_dependencies (alternative format)
            elif "task_dependencies" in analysis:
                dependencies = analysis["task_dependencies"]
            else:
                # Fall back to building from task data
                for task in tasks:
                    dependencies[str(task.id)] = [str(d) for d in task.dependencies]
            
            # Validate dependencies before applying
            if self._validate_dependencies(dependencies, tasks):
                # Apply the optimized dependencies to tasks
                for task in tasks:
                    task_id = str(task.id)
                    if task_id in dependencies:
                        # Clear existing dependencies and set new ones
                        task.dependencies.clear()
                        for dep_id in dependencies[task_id]:
                            try:
                                task.dependencies.append(UUID(dep_id))
                            except ValueError as e:
                                logger.error(f"Invalid UUID format for dependency: {dep_id}, error: {e}")
                                # Skip this dependency to avoid crashing
                                continue
                logger.info("Applied optimized dependencies from analysis")
            else:
                logger.warning("Invalid dependencies detected, keeping original dependencies")
                # Keep original dependencies
                dependencies = {}
                for task in tasks:
                    dependencies[str(task.id)] = [str(d) for d in task.dependencies]
            
            return dependencies
            
        except Exception as e:
            logger.warning(
                "Failed to parse dependency analysis",
                error=str(e),
                response_preview=response.get("content", "No response")[:200]
            )
            # Return basic dependencies from tasks
            dependencies = {}
            for task in tasks:
                dependencies[str(task.id)] = [str(d) for d in task.dependencies]
            return dependencies
    
    def _validate_dependencies(self, dependencies: Dict[str, List[str]], tasks: List[Task]) -> bool:
        """Validate that dependencies don't create cycles or invalid references.
        
        Args:
            dependencies: Proposed dependency mapping
            tasks: List of tasks
            
        Returns:
            True if dependencies are valid
        """
        try:
            # Create a set of valid task IDs
            valid_ids = {str(task.id) for task in tasks}
            
            # Check all dependencies reference valid tasks
            for task_id, dep_ids in dependencies.items():
                if task_id not in valid_ids:
                    logger.warning(f"Invalid task ID in dependencies: {task_id}")
                    return False
                for dep_id in dep_ids:
                    if dep_id not in valid_ids:
                        logger.warning(f"Invalid dependency ID: {dep_id}")
                        return False
            
            # Check for cycles using DFS
            def has_cycle(graph: Dict[str, List[str]]) -> bool:
                visited = set()
                rec_stack = set()
                
                def dfs(node: str) -> bool:
                    visited.add(node)
                    rec_stack.add(node)
                    
                    for neighbor in graph.get(node, []):
                        if neighbor not in visited:
                            if dfs(neighbor):
                                return True
                        elif neighbor in rec_stack:
                            return True
                    
                    rec_stack.remove(node)
                    return False
                
                for node in graph:
                    if node not in visited:
                        if dfs(node):
                            return True
                return False
            
            if has_cycle(dependencies):
                logger.warning("Circular dependency detected")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating dependencies: {e}")
            return False
    
    async def _execute_tasks(
        self,
        tasks: List[Task],
        context: TaskContext
    ) -> None:
        """Execute tasks using sub-agents with retry logic.
        
        Args:
            tasks: Tasks to execute
            context: Execution context
        """
        completed_tasks: Set[UUID] = set()
        failed_tasks: Set[UUID] = set()
        active_agents: Dict[UUID, Agent] = {}
        
        logger.info(f"Starting task execution loop with {len(tasks)} tasks")
        
        while len(completed_tasks) < len(tasks):
            # Get next batch of ready tasks
            ready_tasks = await self.task_manager.get_next_tasks()
            logger.info(f"Got {len(ready_tasks)} ready tasks, {len(active_agents)} active agents")
            
            if not ready_tasks and not active_agents:
                # Check for deadlock
                blocked_tasks = await self.task_manager.get_blocked_tasks()
                if blocked_tasks:
                    # Check if any blocked tasks have failed dependencies
                    truly_deadlocked = []
                    can_skip = []
                    
                    for task in blocked_tasks:
                        has_failed_dep = False
                        for dep_id in task.dependencies:
                            if dep_id in failed_tasks:
                                has_failed_dep = True
                                break
                        
                        if has_failed_dep:
                            can_skip.append(task)
                        else:
                            # Check if waiting for a task that doesn't exist
                            all_task_ids = {t.id for t in tasks}
                            invalid_deps = [d for d in task.dependencies if d not in all_task_ids]
                            if invalid_deps:
                                logger.warning(
                                    f"Task {task.name} has invalid dependencies",
                                    invalid_deps=[str(d) for d in invalid_deps]
                                )
                                can_skip.append(task)
                            else:
                                truly_deadlocked.append(task)
                    
                    # Skip tasks with failed dependencies
                    for task in can_skip:
                        logger.warning(
                            f"Skipping task {task.name} due to failed dependencies",
                            task_id=str(task.id)
                        )
                        await self.task_manager.fail_task(
                            task.id, 
                            "Skipped due to failed dependencies"
                        )
                        failed_tasks.add(task.id)
                        
                        # Create a failed result
                        failed_result = TaskResult(
                            task_id=task.id,
                            agent_id=self.id,
                            success=False
                        )
                        failed_result.add_error("Task skipped due to failed dependencies")
                        self._task_results[task.id] = failed_result
                    
                    # If we still have truly deadlocked tasks, raise error
                    if truly_deadlocked and not can_skip:
                        logger.error(
                            "True deadlock detected",
                            blocked_count=len(truly_deadlocked),
                            blocked_tasks=[t.name for t in truly_deadlocked]
                        )
                        raise TaskError(
                            truly_deadlocked[0].id,
                            "Task execution deadlocked - circular dependencies detected"
                        )
                    
                    # If we skipped some tasks, continue the loop
                    if can_skip:
                        continue
                    
                break
            
            # Spawn agents for ready tasks
            for task in ready_tasks:
                try:
                    agent = await self.spawn_agent(task.required_role or AgentRole.CORE_LOGIC, context)
                    active_agents[agent.id] = agent
                    
                    # Update context with completed tasks for dependency checking
                    context.completed_tasks = completed_tasks.copy()
                    
                    # Execute task with retry logic
                    task_result = await self._execute_task_with_retry(task, agent, context)
                    
                    # Update task status based on result
                    if task_result.success:
                        await self.task_manager.complete_task(task.id, task_result.artifacts)
                        completed_tasks.add(task.id)
                    else:
                        # Task failed after all retries
                        error_msg = "; ".join(task_result.errors) if task_result.errors else "Task failed"
                        await self.task_manager.fail_task(task.id, error_msg)
                        failed_tasks.add(task.id)
                        
                        # Log failure report
                        logger.error(
                            "task_failed_after_retries",
                            task_id=task.id,
                            task_name=task.name,
                            retry_count=self._task_retry_counts.get(task.id, 0),
                            final_error=error_msg
                        )
                    
                    # Remove agent from active list since task is done
                    active_agents.pop(agent.id, None)
                    
                except Exception as e:
                    logger.error(
                        "Failed to spawn agent for task",
                        task_id=str(task.id),
                        task_name=task.name,
                        error=str(e),
                    )
                    await self.task_manager.fail_task(task.id, str(e))
                    failed_tasks.add(task.id)
                    
                    # Create error task result
                    error_result = TaskResult(
                        task_id=task.id,
                        agent_id=uuid4(),
                        success=False,
                    )
                    error_result.add_error(f"Failed to spawn agent: {str(e)}")
                    self._task_results[task.id] = error_result
            
            # Process failed tasks that are eligible for retry
            if failed_tasks and not ready_tasks and not active_agents:
                # Try to resolve deadlock by retrying failed prerequisites
                resolved = await self._try_resolve_deadlock(
                    blocked_tasks if 'blocked_tasks' in locals() else [],
                    failed_tasks,
                    tasks,
                    context
                )
                if resolved:
                    continue
            
            # Wait for some tasks to complete
            if active_agents:
                logger.debug(f"Waiting for {len(active_agents)} active agents to complete tasks")
                await asyncio.sleep(1)  # Poll interval
                
                # Check agent status
                completed_in_round = []
                for agent_id, agent in list(active_agents.items()):
                    status = await agent.report_status()
                    
                    if status["status"] == "idle" and status["current_task"] is None:
                        # Task completed
                        last_task_id = status.get("last_task_id", "")
                        if last_task_id:
                            try:
                                task_id = UUID(last_task_id)
                                artifacts = []
                                for aid in status.get("produced_artifacts", []):
                                    try:
                                        artifacts.append(UUID(aid))
                                    except ValueError as e:
                                        logger.warning(f"Invalid artifact UUID: {aid}, error: {e}")
                                        continue
                                await self.task_manager.complete_task(task_id, artifacts)
                            except ValueError as e:
                                logger.error(f"Invalid task UUID: {last_task_id}, error: {e}")
                                continue
                            await self.coordinator.handle_task_completion(
                                agent_id,
                                task_id,
                                True,
                                status.get("execution_time", 0)
                            )
                            completed_tasks.add(task_id)
                            completed_in_round.append(agent_id)
                
                # Clean up completed agents
                for agent_id in completed_in_round:
                    await self.coordinator.terminate_agent(agent_id)
                    active_agents.pop(agent_id, None)
            
            # Report progress
            progress = await self.task_manager.get_progress()
            logger.info(
                "Execution progress",
                completed=progress["completed_tasks"],
                total=progress["total_tasks"],
                active=len(active_agents),
            )
    
    async def spawn_agents(self, tasks: List[Task], context: TaskContext) -> Result[Dict[UUID, Agent]]:
        """Spawn agents for the given tasks.
        
        Args:
            tasks: List of tasks requiring agents
            context: Execution context
            
        Returns:
            Result containing mapping of agent IDs to agents or error
        """
        try:
            agents = {}
            for task in tasks:
                agent = await self.spawn_agent(task.required_role or AgentRole.CORE_LOGIC, context)
                agents[agent.id] = agent
            return Result.success(agents)
        except Exception as e:
            return Result.failure(
                AgentSpawnError(
                    message=f"Failed to spawn agents: {str(e)}",
                    agent_id=self.id,
                    details={"task_count": len(tasks)}
                )
            )
    
    async def spawn_agent(self, role: AgentRole, context: Optional[TaskContext] = None) -> Agent:
        """Spawn a new sub-agent with specified role.
        
        Args:
            role: Role for the new agent
            context: Optional execution context (uses self.context if not provided)
            
        Returns:
            Newly created agent instance
        """
        # Use provided context or fall back to instance context
        agent_context = context or self.context or TaskContext(project_root=Path("/tmp"))
        
        agent = await self.coordinator.spawn_agent(
            role,
            agent_context,
            metadata={
                "spawned_by": str(self.id),
                "project": self._active_project.get("project_summary", "") if self._active_project else "",
                "project_id": self._current_project_id,
            }
        )
        
        logger.info(
            "Spawned sub-agent",
            agent_id=str(agent.id),
            role=role.value,
            project_id=self._current_project_id,
        )
        
        return agent
    
    async def _execute_task_with_retry(
        self, 
        task: Task, 
        agent: Agent, 
        context: TaskContext
    ) -> TaskResult:
        """Execute a task with retry logic.
        
        Args:
            task: Task to execute
            agent: Agent to execute the task
            context: Execution context
            
        Returns:
            Task result
        """
        task_id = task.id
        if task_id not in self._task_retry_counts:
            self._task_retry_counts[task_id] = 0
            self._task_retry_history[task_id] = []
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                logger.info(
                    "Executing task",
                    task_id=task_id,
                    task_name=task.name,
                    attempt=attempt + 1,
                    max_attempts=self.max_retries
                )
                
                # Execute task
                await self.task_manager.start_task(task_id)
                task_result = await agent.execute_task(task, context)
                
                # Check for success
                if task_result.success:
                    logger.info(
                        "Task executed successfully",
                        task_id=task_id,
                        attempt=attempt + 1
                    )
                    self._task_results[task_id] = task_result
                    return task_result
                
                # Task failed but returned a result
                last_error = Exception("; ".join(task_result.errors) if task_result.errors else "Task failed")
                
                # Analyze failure if diagnosis is enabled
                if self.diagnose_failures:
                    await self._handle_task_failure(
                        task, last_error, agent, attempt + 1, context
                    )
                
            except Exception as e:
                last_error = e
                logger.warning(
                    "Task execution failed",
                    task_id=task_id,
                    attempt=attempt + 1,
                    error=str(e)
                )
                
                # Analyze failure
                if self.diagnose_failures:
                    await self._handle_task_failure(
                        task, e, agent, attempt + 1, context
                    )
            
            # Check if we should retry
            self._task_retry_counts[task_id] = attempt + 1
            
            if attempt < self.max_retries - 1:
                # Determine retry delay
                retry_delay = await self._calculate_retry_delay(
                    task, last_error, attempt + 1
                )
                
                logger.info(
                    f"Retrying task in {retry_delay} seconds",
                    task_id=task_id
                )
                await asyncio.sleep(retry_delay)
                
                # Modify task for retry if needed
                await self._prepare_task_for_retry(task, last_error, attempt + 1)
        
        # All retries exhausted
        error_result = TaskResult(
            task_id=task_id,
            agent_id=agent.id,
            success=False,
        )
        error_msg = f"Failed after {self.max_retries} attempts: {str(last_error)}"
        error_result.add_error(error_msg)
        self._task_results[task_id] = error_result
        
        return error_result
    
    async def _handle_task_failure(
        self,
        task: Task,
        error: Exception,
        agent: Agent,
        attempt: int,
        context: TaskContext
    ) -> None:
        """Handle a task failure by analyzing and logging it.
        
        Args:
            task: Failed task
            error: The error that occurred
            agent: Agent that executed the task
            attempt: Attempt number
            context: Execution context
        """
        # Get CLI response if available
        cli_response = None
        if hasattr(agent, '_last_cli_response'):
            cli_response = agent._last_cli_response
        
        # Analyze error
        diagnosis_context = {
            "attempt": attempt,
            "max_attempts": self.max_retries,
            "agent_id": agent.id,
            "cli_response": cli_response,
            "error_message": str(error),
            "base_delay": self.retry_delay,
            "backoff_multiplier": self.retry_backoff,
        }
        
        diagnosis = await self.failure_analyzer.analyze_error(
            task, error, diagnosis_context
        )
        
        # Record retry history
        self._task_retry_history[task.id].append({
            "attempt": attempt,
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(error),
            "diagnosis": diagnosis,
            "cli_response": cli_response,
        })
        
        # Log structured failure information
        logger.error(
            "task_retry_failure",
            task_id=task.id,
            task_name=task.name,
            attempt=attempt,
            error_type=diagnosis.error_type.value,
            is_retryable=diagnosis.is_retryable,
            retry_strategy=diagnosis.retry_strategy.value,
            suggested_fix=diagnosis.suggested_fix
        )
    
    async def _calculate_retry_delay(
        self,
        task: Task,
        error: Exception,
        attempt: int
    ) -> float:
        """Calculate delay before retry.
        
        Args:
            task: Failed task
            error: The error that occurred
            attempt: Attempt number
            
        Returns:
            Delay in seconds
        """
        # Check if we have a specific retry delay from diagnosis
        if task.id in self._task_retry_history and self._task_retry_history[task.id]:
            last_diagnosis = self._task_retry_history[task.id][-1].get("diagnosis")
            if last_diagnosis and hasattr(last_diagnosis, "retry_delay"):
                return last_diagnosis.retry_delay
        
        # Default exponential backoff
        return min(
            self.retry_delay * (self.retry_backoff ** (attempt - 1)),
            60.0  # Max 60 seconds
        )
    
    async def _prepare_task_for_retry(
        self,
        task: Task,
        error: Exception,
        attempt: int
    ) -> None:
        """Prepare a task for retry by potentially modifying it.
        
        Args:
            task: Task to retry
            error: The error that occurred
            attempt: Attempt number
        """
        # Get last diagnosis
        if task.id not in self._task_retry_history or not self._task_retry_history[task.id]:
            return
        
        last_record = self._task_retry_history[task.id][-1]
        diagnosis = last_record.get("diagnosis")
        
        if not diagnosis:
            return
        
        # Modify task based on retry strategy
        if diagnosis.retry_strategy == RetryStrategy.MODIFY_PROMPT:
            # Generate improved prompt
            new_description = await self.failure_analyzer.generate_fix_prompt(
                task, diagnosis
            )
            task.description = new_description
            logger.info(
                "Modified task prompt for retry",
                task_id=task.id,
                strategy="modify_prompt"
            )
        
        elif diagnosis.retry_strategy == RetryStrategy.SIMPLIFY_TASK:
            # Simplify the task
            task.description = await self.failure_analyzer.generate_fix_prompt(
                task, diagnosis
            )
            logger.info(
                "Simplified task for retry",
                task_id=task.id,
                strategy="simplify_task"
            )
        
        elif diagnosis.retry_strategy == RetryStrategy.INCREASE_TIMEOUT:
            # Increase timeout in context if possible
            if hasattr(task, "timeout"):
                task.timeout = task.timeout * 1.5
                logger.info(
                    "Increased task timeout for retry",
                    task_id=task.id,
                    new_timeout=task.timeout
                )
    
    async def _try_resolve_deadlock(
        self,
        blocked_tasks: List[Task],
        failed_tasks: Set[UUID],
        all_tasks: List[Task],
        context: TaskContext
    ) -> bool:
        """Try to resolve deadlock by retrying failed prerequisite tasks.
        
        Args:
            blocked_tasks: Tasks that are blocked
            failed_tasks: Set of failed task IDs
            all_tasks: All tasks in the project
            context: Execution context
            
        Returns:
            True if deadlock might be resolved
        """
        if not blocked_tasks or not failed_tasks:
            return False
        
        # Find failed tasks that are blocking others
        task_map = {task.id: task for task in all_tasks}
        blocking_failed_tasks = set()
        
        for blocked_task in blocked_tasks:
            for dep_id in blocked_task.dependencies:
                if dep_id in failed_tasks:
                    blocking_failed_tasks.add(dep_id)
        
        if not blocking_failed_tasks:
            return False
        
        logger.info(
            "Attempting to resolve deadlock by retrying failed prerequisites",
            failed_prerequisites=len(blocking_failed_tasks)
        )
        
        # Reset failed prerequisite tasks for retry
        for task_id in blocking_failed_tasks:
            if await self.task_manager.reset_task(task_id):
                failed_tasks.remove(task_id)
                # Reset retry count for fresh attempt
                self._task_retry_counts[task_id] = 0
        
        return True
    
    async def assign_task(self, task: Task, agent: Agent) -> None:
        """Assign a task to an agent.
        
        Args:
            task: Task to assign
            agent: Agent to receive the task
        """
        # Create detailed task specification
        spec_prompt = get_decomposition_prompt("task_specification")
        
        prompt_vars = {
            "task_id": str(task.id),
            "task_name": task.name,
            "task_description": task.description,
            "deliverable": task.metadata.get("deliverable", ""),
            "project_context": json.dumps(self._active_project or {}, indent=2),
            "completed_dependencies": json.dumps(
                [str(d) for d in task.dependencies if d in self.task_manager._completed_tasks],
                indent=2
            ),
        }
        
        prompt = spec_prompt.render(**prompt_vars)
        
        response = await _await_if_needed(self.ai_client.create_message(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2048,
        ))
        
        try:
            specification = json.loads(response["content"])
            task.metadata["full_specification"] = specification
        except Exception as e:
            logger.warning(
                "Failed to generate task specification",
                task_id=str(task.id),
                error=str(e),
            )
        
        # Assign via coordinator
        await self.coordinator.assign_task(agent.id, task)
    
    async def monitor_progress(self) -> Dict[str, Any]:
        """Monitor overall system progress.
        
        Returns:
            Progress report with task statuses and metrics
        """
        # Get various progress reports
        task_progress = await self.task_manager.get_progress()
        system_status = await self.coordinator.get_system_status()
        
        # Get task details
        all_tasks = await self.task_manager._queue.get_all_tasks()
        active_tasks = [t for t in all_tasks if t.status == TaskStatus.IN_PROGRESS]
        completed_tasks = [t for t in all_tasks if t.status == TaskStatus.COMPLETED]
        failed_tasks = [t for t in all_tasks if t.status == TaskStatus.FAILED]
        
        # Use AI to aggregate progress
        prompt = PROGRESS_AGGREGATION_PROMPT.render(
            active_tasks_json=json.dumps([t.model_dump() for t in active_tasks], indent=2),
            completed_tasks_json=json.dumps([t.model_dump() for t in completed_tasks], indent=2),
            failed_tasks_json=json.dumps([t.model_dump() for t in failed_tasks], indent=2),
            project_summary=self._active_project.get("project_summary", "") if self._active_project else "",
        )
        
        response = await _await_if_needed(self.ai_client.create_message(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1024,
        ))
        
        try:
            aggregated = json.loads(response["content"])
        except:
            aggregated = {}
        
        return {
            "task_progress": task_progress,
            "system_status": system_status,
            "aggregated_analysis": aggregated,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    async def handle_failure(self, task: Task, error: str) -> List[Task]:
        """Handle task failure and generate repair tasks.
        
        Args:
            task: Failed task
            error: Error message
            
        Returns:
            List of repair tasks
        """
        logger.info(
            "Handling task failure",
            task_id=str(task.id),
            task_name=task.name,
            error=error,
        )
        
        # Analyze the failure
        analysis_prompt = f"""A task has failed in the coding system. Analyze the failure and suggest repair tasks.

FAILED TASK:
Name: {task.name}
Description: {task.description}
Error: {error}

CONTEXT:
{json.dumps(task.metadata, indent=2)}

Suggest specific repair tasks that could fix this issue. Output as JSON:
{{
    "failure_analysis": "What went wrong",
    "repair_tasks": [
        {{
            "name": "Repair task name",
            "description": "What needs to be done",
            "agent_type": "core_logic|testing|debugging",
            "priority": "high|medium|low"
        }}
    ]
}}"""
        
        response = await _await_if_needed(self.ai_client.create_message(
            messages=[{"role": "user", "content": analysis_prompt}],
            temperature=0.3,
            max_tokens=1024,
        ))
        
        try:
            analysis = json.loads(response["content"])
            
            # Create repair tasks
            repair_tasks = []
            for repair_def in analysis.get("repair_tasks", []):
                repair_task = Task(
                    name=f"Repair: {repair_def['name']}",
                    description=repair_def["description"],
                    priority=TaskPriority.HIGH,  # Repairs are high priority
                    dependencies=[task.id],  # Depend on failed task
                    required_role=self._get_agent_role(repair_def.get("agent_type", "debugging")),
                    metadata={
                        "is_repair": True,
                        "original_task_id": str(task.id),
                        "failure_reason": error,
                        "repair_strategy": repair_def,
                    }
                )
                repair_tasks.append(repair_task)
            
            # Add repair tasks to system
            if repair_tasks:
                await self.task_manager.add_tasks(repair_tasks)
            
            return repair_tasks
            
        except Exception as e:
            logger.error(
                "Failed to generate repair tasks",
                error=str(e),
            )
            return []
    
    async def coordinate_execution(self, tasks: List[Task], context: TaskContext) -> Result[Dict[UUID, TaskResult]]:
        """Coordinate the execution of tasks by managing agents.
        
        This method handles the core orchestration logic including:
        - Agent lifecycle management
        - Task assignment based on agent capabilities
        - Parallel execution where possible
        - Result collection
        
        Args:
            tasks: List of tasks to execute
            context: Execution context with artifact manager
            
        Returns:
            Result containing dictionary mapping task IDs to task results or error
        """
        try:
            # Track task results
            task_results: Dict[UUID, TaskResult] = {}
            
            # Use the existing _execute_tasks method for coordination
            await self._execute_tasks(tasks, context)
            
            # Collect results from agents
            for task in tasks:
                if task.id in self._task_results:
                    # Use stored task result
                    task_results[task.id] = self._task_results[task.id]
                else:
                    # Create a default result for tasks without stored results
                    task_result = TaskResult(
                        task_id=task.id,
                        agent_id=task.assigned_agent_id or uuid4(),
                        success=(task.status == TaskStatus.COMPLETED),
                        artifacts=task.artifacts,
                        execution_time=0.0,
                    )
                    
                    if task.status == TaskStatus.FAILED:
                        task_result.add_error(task.error_message or "Unknown error")
                    
                    task_results[task.id] = task_result
            
            return Result.success(task_results)
            
        except TaskError as e:
            return Result.failure(
                OrchestrationError(
                    message=f"Task execution failed: {str(e)}",
                    agent_id=self.id,
                    task_id=e.task_id if hasattr(e, 'task_id') else None,
                    details={"task_count": len(tasks)}
                )
            )
        except Exception as e:
            return Result.failure(
                OrchestrationError(
                    message=f"Failed to coordinate execution: {str(e)}",
                    agent_id=self.id,
                    details={"task_count": len(tasks)}
                )
            )
    
    async def aggregate_results(self, task_results: Dict[UUID, TaskResult]) -> Result[ProjectResult]:
        """Aggregate all task results into a final project result.
        
        Combines all artifacts and metrics into a cohesive result that
        can be presented to the user.
        
        Args:
            task_results: Dictionary mapping task IDs to TaskResults
            
        Returns:
            Result containing aggregated project result or error
        """
        try:
            # Collect all artifact IDs from task results
            all_artifact_ids = []
            for result in task_results.values():
                all_artifact_ids.extend(result.artifacts)
            
            # Fetch actual artifacts from storage
            all_artifacts = []
            if self.artifact_manager:
                for artifact_id in all_artifact_ids:
                    try:
                        artifact = await self.artifact_manager.get_artifact(artifact_id)
                        if artifact:
                            all_artifacts.append(artifact)
                    except Exception as e:
                        logger.warning(f"Failed to retrieve artifact {artifact_id}: {e}")
            
            # Get task statistics
            completed = sum(1 for r in task_results.values() if r.success)
            failed = sum(1 for r in task_results.values() if not r.success)
            total = len(task_results)
            
            execution_time = (
                datetime.utcnow() - self._start_time
            ).total_seconds() if self._start_time else 0
            
            # Collect all errors and warnings
            all_errors = []
            all_warnings = []
            for result in task_results.values():
                all_errors.extend(result.errors)
                all_warnings.extend(result.warnings)
            
            # Collect retry information
            retry_summary = {}
            failure_reports = []
            
            for task_id, retry_count in self._task_retry_counts.items():
                if retry_count > 0:
                    retry_summary[task_id] = retry_count
                    
                    # Add failure report if task failed
                    if task_id in task_results and not task_results[task_id].success:
                        task_history = self._task_retry_history.get(task_id, [])
                        failure_reports.append({
                            "task_id": str(task_id),
                            "retry_count": retry_count,
                            "attempts": task_history,
                            "final_error": task_results[task_id].errors[0] if task_results[task_id].errors else "Unknown error"
                        })
            
            project_result = ProjectResult(
                project_name=self._current_project_id or "unnamed_project",
                success=failed == 0,
                artifacts=all_artifacts,
                execution_time=execution_time,
                tasks_completed=completed,
                tasks_failed=failed,
                success_rate=completed / total if total > 0 else 0,
                retry_summary=retry_summary,
                failure_reports=failure_reports,
                metadata={
                    "project_id": self._current_project_id,
                    "project_summary": self._active_project.get("project_summary", "") if self._active_project else "",
                    "total_tasks": total,
                    "artifact_count": len(all_artifacts),
                    "errors": all_errors,
                    "warnings": all_warnings,
                    "task_results": {
                        str(task_id): {
                            "success": result.success,
                            "artifacts": len(result.artifacts),
                            "execution_time": result.execution_time,
                        }
                        for task_id, result in task_results.items()
                    },
                }
            )
            
            return Result.success(project_result)
            
        except Exception as e:
            return Result.failure(
                ResultAggregationError(
                    message=f"Failed to aggregate results: {str(e)}",
                    agent_id=self.id,
                    details={
                        "task_count": len(task_results),
                        "project_id": self._current_project_id
                    }
                )
            )
    
    async def _aggregate_results(self) -> ProjectResult:
        """Aggregate results from all tasks.
        
        Returns:
            Project execution result
        """
        all_tasks = await self.task_manager._queue.get_all_tasks()
        
        # Collect artifacts
        artifacts = []
        for task in all_tasks:
            if task.status == TaskStatus.COMPLETED:
                # In a real system, we would fetch actual artifacts
                # For now, we'll create placeholder artifacts
                for artifact_id in task.artifacts:
                    # Placeholder artifact
                    artifacts.append(Artifact(
                        id=artifact_id,
                        type=ArtifactType.SOURCE_CODE,
                        name=f"{task.name.lower().replace(' ', '_')}.py",
                        path=Path(f"src/{task.name.lower().replace(' ', '_')}.py"),
                        content="# Generated code",
                        task_id=task.id,
                        agent_id=uuid4(),
                    ))
        
        # Calculate metrics
        completed = len([t for t in all_tasks if t.status == TaskStatus.COMPLETED])
        failed = len([t for t in all_tasks if t.status == TaskStatus.FAILED])
        total = len(all_tasks)
        
        execution_time = (
            datetime.utcnow() - self._start_time
        ).total_seconds() if self._start_time else 0
        
        return ProjectResult(
            artifacts=artifacts,
            execution_time=execution_time,
            tasks_completed=completed,
            tasks_failed=failed,
            success_rate=completed / total if total > 0 else 0,
            metadata={
                "project_summary": self._active_project.get("project_summary", "") if self._active_project else "",
                "total_tasks": total,
                "critical_path": [str(t.id) for t in await self.task_manager.get_critical_path()],
            }
        )
    
    def _get_priority(self, complexity: str) -> TaskPriority:
        """Convert complexity to priority.
        
        Args:
            complexity: Task complexity (simple/medium/complex)
            
        Returns:
            Task priority
        """
        priority_map = {
            "simple": TaskPriority.LOW,
            "medium": TaskPriority.MEDIUM,
            "complex": TaskPriority.HIGH,
        }
        return priority_map.get(complexity, TaskPriority.MEDIUM)
    
    async def _generate_project_name(self, user_request: str) -> str:
        """Generate a short 1-2 word project name from the user request.
        
        Args:
            user_request: The user's request
            
        Returns:
            Short project name
        """
        try:
            # Create the prompt for o3
            prompt = f"""Generate a SHORT project name (2-4 words) for this request:
"{user_request}"

Examples:
- "Create a hello world script" -> "hello_world_script"
- "Build a calculator" -> "calculator_app"

Return ONLY the project name, nothing else."""
            
            logger.info(f"Sending prompt to o3: {prompt}")
            
            response = await _await_if_needed(self.ai_client.create_message(
                messages=[{"role": "user", "content": prompt}],
                temperature=1.0,  # o3 only supports temperature=1
                max_tokens=200,  # o3 needs more tokens for reasoning + output
            ))
            project_name = response["content"].strip().lower()
            
            logger.info(f"o3 response: '{project_name}' (length: {len(project_name)})")
            
            # Clean the response
            import re
            # Remove quotes if present
            project_name = project_name.strip('"').strip("'")
            # Ensure valid characters
            project_name = re.sub(r'[^\w]+', '_', project_name)
            project_name = project_name.strip('_')
            
            # Limit to 3-4 words for better descriptiveness
            words = project_name.split('_')[:4]
            project_name = '_'.join(words)
            
            # Fallback if empty
            if not project_name:
                logger.warning("AI returned empty project name, using fallback")
                raise ValueError("Empty project name from AI")
                
            return project_name
            
        except Exception as e:
            logger.warning(f"Failed to generate project name: {e}")
            # Better fallback: extract meaningful words from request
            import re
            words = re.findall(r'\b\w+\b', user_request.lower())
            # Skip common words
            skip_words = {'create', 'make', 'build', 'write', 'generate', 'develop', 
                         'implement', 'a', 'an', 'the', 'that', 'with', 'for', 'and', 
                         'or', 'but', 'in', 'on', 'at', 'to', 'from', 'simple', 'basic',
                         'new', 'small', 'big', 'large', 'tiny', 'using', 'use'}
            
            # Extract meaningful words
            meaningful_words = []
            for w in words:
                if w not in skip_words and len(w) > 2:
                    meaningful_words.append(w)
                    if len(meaningful_words) >= 3:
                        break
            
            # Special handling for common patterns
            if 'hello' in words and 'world' in words:
                project_name = 'hello_world'
                if 'python' in words:
                    project_name += '_python'
                elif 'script' in words:
                    project_name += '_script'
            elif 'calculator' in words:
                project_name = 'calculator'
                if 'add' in words or 'subtract' in words:
                    project_name += '_app'
            elif 'weather' in words:
                project_name = 'weather'
                if 'api' in words or 'client' in words:
                    project_name += '_client'
                elif 'app' in words:
                    project_name += '_app'
            elif 'todo' in words or 'task' in words:
                project_name = 'todo_list'
                if 'app' in words or 'application' in words:
                    project_name += '_app'
            elif meaningful_words:
                project_name = '_'.join(meaningful_words)
            else:
                # Absolute fallback
                project_name = 'project'
                
            logger.info(f"Generated project name: {project_name}")
            return project_name
    
    def _get_agent_role(self, agent_type: str) -> AgentRole:
        """Convert agent type string to role.
        
        Args:
            agent_type: Agent type string
            
        Returns:
            Agent role enum
        """
        role_map = {
            "core_logic": AgentRole.CORE_LOGIC,
            "testing": AgentRole.TESTING,
            "documentation": AgentRole.DOCUMENTATION,
            "optimization": AgentRole.OPTIMIZATION,
            "debugging": AgentRole.VERIFICATION,
            "verification": AgentRole.VERIFICATION,
        }
        return role_map.get(agent_type, AgentRole.CORE_LOGIC)
    
    async def _initialize_project_storage(self, user_request: str) -> str:
        """Initialize storage for a new project.
        
        Args:
            user_request: The user's request
            
        Returns:
            Project ID
        """
        # Generate human-readable project ID from request
        import re
        
        # Generate a short project name
        project_name = await self._generate_project_name(user_request)
        
        # Check for existing projects with the same name
        existing_projects = []
        if self.artifact_storage_path.exists():
            for project_dir in self.artifact_storage_path.iterdir():
                if project_dir.is_dir() and project_dir.name.startswith(project_name):
                    existing_projects.append(project_dir.name)
        
        # Determine the project ID with numbering if needed
        if not existing_projects:
            project_id = project_name
        else:
            # Find the highest number
            max_num = 1
            for existing in existing_projects:
                if existing == project_name:
                    max_num = max(max_num, 2)
                elif existing.startswith(f"{project_name}_") and existing[len(project_name)+1:].isdigit():
                    try:
                        num = int(existing[len(project_name)+1:])
                        max_num = max(max_num, num + 1)
                    except ValueError:
                        pass
            project_id = f"{project_name}_{max_num}"
        
        # Create project directory structure
        project_path = self.artifact_storage_path / project_id
        project_path.mkdir(parents=True, exist_ok=True)
        
        # Create workspace directory where all files will live
        workspace_path = project_path / "workspace"
        workspace_path.mkdir(exist_ok=True)
        
        # Create artifacts directory for version history
        artifacts_path = project_path / "artifacts"
        artifacts_path.mkdir(exist_ok=True)
        
        # Store paths for later use
        self._project_path = project_path
        self._workspace_path = workspace_path
        
        # Create project metadata
        project_metadata = {
            "id": project_id,
            "request": user_request,
            "created_at": datetime.utcnow().isoformat(),
            "status": "in_progress",
        }
        
        # Save project metadata
        metadata_path = project_path / "project_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(project_metadata, f, indent=2)
        
        logger.info(
            "Initialized project storage",
            project_id=project_id,
            project_path=str(project_path),
        )
        
        return project_id
    
    async def _store_execution_artifacts(self, task_results: Dict[UUID, TaskResult]) -> None:
        """Store all artifacts from task execution.
        
        Args:
            task_results: Task execution results
        """
        if not self._current_project_id:
            logger.warning("No project ID set, skipping artifact storage")
            return
        
        # Project artifacts are already stored by sub-agents during execution
        # This method ensures all artifacts are properly linked to the project
        
        total_artifacts = sum(len(result.artifacts) for result in task_results.values())
        logger.info(
            "Artifacts stored for project",
            project_id=self._current_project_id,
            total_artifacts=total_artifacts,
        )
    
    async def _create_project_manifest(
        self,
        user_request: str,
        task_results: Dict[UUID, TaskResult]
    ) -> Optional[Artifact]:
        """Create a manifest artifact summarizing the project.
        
        Args:
            user_request: Original user request
            task_results: Task execution results
            
        Returns:
            Manifest artifact or None if failed
        """
        if not self._current_project_id:
            return None
        
        # Collect project information
        manifest_data = {
            "project_id": self._current_project_id,
            "request": user_request,
            "created_at": self._start_time.isoformat() if self._start_time else None,
            "completed_at": datetime.utcnow().isoformat(),
            "summary": self._active_project.get("project_summary", "") if self._active_project else "",
            "tasks": [
                {
                    "task_id": str(task_id),
                    "success": result.success,
                    "artifacts": [str(aid) for aid in result.artifacts],
                    "execution_time": result.execution_time,
                    "errors": result.errors,
                }
                for task_id, result in task_results.items()
            ],
            "statistics": {
                "total_tasks": len(task_results),
                "successful_tasks": sum(1 for r in task_results.values() if r.success),
                "failed_tasks": sum(1 for r in task_results.values() if not r.success),
                "total_artifacts": sum(len(r.artifacts) for r in task_results.values()),
            },
        }
        
        # Create manifest artifact
        manifest = Artifact(
            name=f"{self._current_project_id}_manifest.json",
            type=ArtifactType.DOCUMENTATION,
            content=json.dumps(manifest_data, indent=2),
            path=Path(f"{self._current_project_id}_manifest.json"),
            language="json",
            task_id=uuid4(),  # Special task ID for meta-level artifacts
            agent_id=self.id,
            metadata={
                "is_manifest": True,
                "project_id": self._current_project_id,
            },
        )
        
        # Store the manifest
        if self.artifact_manager:
            try:
                stored = await self.artifact_manager.store_artifact(manifest)
                self._project_artifacts.append(stored)
                logger.info(
                    "Created project manifest",
                    project_id=self._current_project_id,
                    manifest_id=str(stored.id),
                )
                return stored
            except Exception as e:
                logger.error(
                    "Failed to store project manifest",
                    error=str(e),
                    exc_info=True,
                )
        
        return None
    
    async def _get_project_artifacts(self, project_id: str) -> List[Artifact]:
        """Get all artifacts for a project.
        
        Args:
            project_id: Project ID
            
        Returns:
            List of project artifacts
        """
        if not self.artifact_manager:
            return []
        
        try:
            # Search for artifacts by project ID
            results = await self.artifact_manager.search_artifacts(
                metadata_filters={"project_id": project_id}
            )
            return results
        except Exception as e:
            logger.error(
                "Failed to get project artifacts",
                project_id=project_id,
                error=str(e),
            )
            return []
    
    async def _export_project(
        self,
        project_id: str,
        export_path: Path,
        include_metadata: bool = True
    ) -> bool:
        """Export all project artifacts to a directory.
        
        Args:
            project_id: Project ID
            export_path: Path to export to
            include_metadata: Whether to include metadata files
            
        Returns:
            True if successful
        """
        try:
            # Create export directory
            export_path.mkdir(parents=True, exist_ok=True)
            
            # Get all project artifacts
            artifacts = await self._get_project_artifacts(project_id)
            
            # Export each artifact
            for artifact in artifacts:
                artifact_path = export_path / artifact.name
                
                # Write artifact content
                with open(artifact_path, "w", encoding="utf-8") as f:
                    f.write(artifact.content)
                
                # Write metadata if requested
                if include_metadata:
                    metadata_path = export_path / f"{artifact.name}.metadata.json"
                    with open(metadata_path, "w") as f:
                        json.dump(
                            {
                                "id": str(artifact.id),
                                "type": artifact.type.value,
                                "version": artifact.version,
                                "created_at": artifact.created_at.isoformat(),
                                "task_id": str(artifact.task_id),
                                "agent_id": str(artifact.agent_id),
                                "metadata": artifact.metadata,
                            },
                            f,
                            indent=2,
                        )
            
            logger.info(
                "Exported project artifacts",
                project_id=project_id,
                export_path=str(export_path),
                artifact_count=len(artifacts),
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "Failed to export project",
                project_id=project_id,
                error=str(e),
                exc_info=True,
            )
            return False
    
    async def shutdown(self) -> None:
        """Shutdown the Meta Agent and all sub-systems."""
        logger.info("Shutting down MetaAgent")
        
        # Stop coordinator
        await self.coordinator.stop()
        
        # Close AI client
        await self.ai_client.close()
        
        # Unregister from communication
        await self.communication_hub.unregister_agent(self.id)
        
        logger.info("MetaAgent shutdown complete")