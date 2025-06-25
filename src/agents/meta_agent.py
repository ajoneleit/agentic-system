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

from config import get_settings, ClaudeModel
from src.agents.sub_agent import (
    CodeGeneratorAgent,
    DebugAgent,
    DocumentationAgent,
    RefactorAgent,
    TestWriterAgent,
)
from src.clients.claude_client import ClaudeClient
from src.core.artifact_manager import ArtifactManager
from src.core.communication import CommunicationHub, MessageType
from src.core.coordinator import AgentCoordinator
from src.core.dependency_tracker import DependencyTracker
from src.core.exceptions import (
    TaskDecompositionError,
    TaskError,
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
from src.prompts.task_decomposition import (
    get_decomposition_prompt,
    TASK_ANALYSIS_PROMPT,
    DEPENDENCY_ANALYSIS_PROMPT,
    PROGRESS_AGGREGATION_PROMPT,
)
from src.utils.app_logging import log_execution_time


logger = get_logger(__name__)


@dataclass
class ProjectResult:
    """Result of processing a user request."""
    
    artifacts: List[Artifact]
    execution_time: float
    tasks_completed: int
    tasks_failed: int
    success_rate: float
    metadata: Dict[str, Any] = field(default_factory=dict)


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
        self.claude_client = ClaudeClient()
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
        
        logger.info("MetaAgent initialized")
    
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
    async def process_request(self, user_request: str) -> ProjectResult:
        """Process a user request end-to-end.
        
        Args:
            user_request: User's coding request
            
        Returns:
            Project execution result
        """
        self._start_time = datetime.utcnow()
        logger.info("Processing user request", request_length=len(user_request))
        
        try:
            # 1. Initialize project storage
            project_id = await self._initialize_project_storage(user_request)
            self._current_project_id = project_id
            logger.info("Initialized project storage", project_id=project_id)
            
            # 2. Decompose the request into tasks
            tasks = await self.decompose_task(user_request)
            logger.info(f"Decomposed into {len(tasks)} tasks")
            
            # 3. Add tasks to task manager
            await self.task_manager.add_tasks(tasks)
            
            # 4. Create execution context with artifact manager
            context = TaskContext(
                project_root=self.context.project_root if self.context and hasattr(self.context, 'project_root') else self._project_path,
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
                artifact_naming_convention="{name}_{task_name}_{timestamp}",
                enable_artifact_caching=True,
                auto_version_on_change=True,
                link_test_artifacts=True,
            )
            
            # 5. Execute tasks using the coordination method
            task_results = await self.coordinate_execution(tasks, context)
            
            # 6. Store execution artifacts
            await self._store_execution_artifacts(task_results)
            
            # 7. Create project manifest
            manifest = await self._create_project_manifest(user_request, task_results)
            
            # 8. Aggregate results
            result = await self.aggregate_results(task_results)
            
            logger.info(
                "Request processing complete",
                project_id=project_id,
                tasks_completed=result.tasks_completed,
                tasks_failed=result.tasks_failed,
                execution_time=result.execution_time,
            )
            
            return result
            
        except Exception as e:
            logger.error(
                "Failed to process request",
                error=str(e),
                exc_info=True,
            )
            raise
    
    async def decompose_task(self, user_prompt: str) -> List[Task]:
        """Decompose user prompt into executable tasks.
        
        Args:
            user_prompt: User's request
            
        Returns:
            List of decomposed tasks with dependencies
        """
        try:
            # Use Claude to analyze the request
            prompt = TASK_ANALYSIS_PROMPT.render(user_request=user_prompt)
            
            response = await self.claude_client.create_message(
                model=ClaudeModel.OPUS,  # Use most capable model for decomposition
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4096,
            )
            
            # Parse the response
            if not response.content or not response.content[0].text:
                raise ValueError("Empty response from Claude")
                
            response_text = response.content[0].text.strip()
            
            # Try to extract JSON from the response
            try:
                analysis = json.loads(response_text)
            except json.JSONDecodeError:
                # Try to find JSON in the response
                import re
                # Look for JSON object that starts with { and ends with }
                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
                if json_match:
                    try:
                        analysis = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        logger.error(
                            "Found JSON-like content but failed to parse",
                            json_content=json_match.group()[:500]
                        )
                        raise ValueError("Invalid JSON structure in response")
                else:
                    logger.error(
                        "Failed to find valid JSON in Claude response",
                        response_preview=response_text[:500],
                        response_length=len(response_text)
                    )
                    raise ValueError("No valid JSON found in response")
            
            self._active_project = analysis
            
            # Create Task objects
            tasks = []
            task_map = {}  # name -> Task mapping for dependencies
            
            for task_def in analysis["tasks"]:
                task = Task(
                    name=task_def["name"],
                    description=task_def["description"],
                    priority=self._get_priority(task_def["complexity"]),
                    estimated_complexity=task_def["complexity"],
                    required_role=self._get_agent_role(task_def["agent_type"]),
                    metadata={
                        "specification": task_def,
                        "deliverable": task_def["deliverable"],
                        "requirements": task_def.get("requirements", {}),
                    }
                )
                tasks.append(task)
                task_map[task.name] = task
            
            # Set dependencies
            for task_def, task in zip(analysis["tasks"], tasks):
                for dep_name in task_def.get("dependencies", []):
                    if dep_name in task_map:
                        task.dependencies.append(task_map[dep_name].id)
            
            # Analyze dependencies for optimization
            await self._analyze_dependencies(tasks)
            
            return tasks
            
        except Exception as e:
            logger.error(
                "Task decomposition failed",
                error=str(e),
                exc_info=True,
            )
            raise TaskDecompositionError(
                task_id=uuid4(),
                user_prompt=user_prompt,
                reason=str(e)
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
        
        response = await self.claude_client.create_message(
            model=ClaudeModel.OPUS,  # Use OPUS for all meta-agent tasks
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2048,
        )
        
        # Parse and apply optimizations
        try:
            response_text = response.content[0].text.strip()
            logger.debug(f"Raw dependency analysis response: {response_text[:200]}...")
            
            # Try to extract JSON if there's extra text
            if response_text.startswith('{'):
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
                        dep_ids = [name_to_id[dep_name] for dep_name in deps_names if dep_name in name_to_id]
                        dependencies[task_id] = dep_ids
            # Check for task_dependencies (alternative format)
            elif "task_dependencies" in analysis:
                dependencies = analysis["task_dependencies"]
            else:
                # Fall back to building from task data
                for task in tasks:
                    dependencies[str(task.id)] = [str(d) for d in task.dependencies]
            
            return dependencies
            
        except Exception as e:
            logger.warning(
                "Failed to parse dependency analysis",
                error=str(e),
                response_preview=response.content[0].text[:200] if response and response.content else "No response"
            )
            # Return basic dependencies from tasks
            dependencies = {}
            for task in tasks:
                dependencies[str(task.id)] = [str(d) for d in task.dependencies]
            return dependencies
    
    async def _execute_tasks(
        self,
        tasks: List[Task],
        context: TaskContext
    ) -> None:
        """Execute tasks using sub-agents.
        
        Args:
            tasks: Tasks to execute
            context: Execution context
        """
        completed_tasks: Set[UUID] = set()
        active_agents: Dict[UUID, Agent] = {}
        
        while len(completed_tasks) < len(tasks):
            # Get next batch of ready tasks
            ready_tasks = await self.task_manager.get_next_tasks()
            
            if not ready_tasks and not active_agents:
                # Check for deadlock
                blocked_tasks = await self.task_manager.get_blocked_tasks()
                if blocked_tasks:
                    logger.error(
                        "Deadlock detected",
                        blocked_count=len(blocked_tasks),
                        blocked_tasks=[t.name for t in blocked_tasks],
                    )
                    raise TaskError(
                        blocked_tasks[0].id,
                        "Task execution deadlocked"
                    )
                break
            
            # Spawn agents for ready tasks
            for task in ready_tasks:
                try:
                    agent = await self.spawn_agent(task.required_role or AgentRole.CORE_LOGIC, context)
                    active_agents[agent.id] = agent
                    
                    # Start task execution
                    await self.task_manager.start_task(task.id)
                    
                    # Execute task and get result
                    try:
                        task_result = await agent.execute_task(task, context)
                        self._task_results[task.id] = task_result
                        
                        # Update task status based on result
                        if task_result.success:
                            await self.task_manager.complete_task(task.id, task_result.artifacts)
                            completed_tasks.add(task.id)
                        else:
                            error_msg = "; ".join(task_result.errors) if task_result.errors else "Task failed"
                            await self.task_manager.fail_task(task.id, error_msg)
                            completed_tasks.add(task.id)
                        
                        # Remove agent from active list since task is done
                        active_agents.pop(agent.id, None)
                        
                    except Exception as exec_error:
                        logger.error(
                            "Task execution failed",
                            task_id=str(task.id),
                            error=str(exec_error),
                            exc_info=True,
                        )
                        await self.task_manager.fail_task(task.id, str(exec_error))
                        completed_tasks.add(task.id)
                        
                        # Create error task result
                        error_result = TaskResult(
                            task_id=task.id,
                            agent_id=agent.id,
                            success=False,
                        )
                        error_result.add_error(str(exec_error))
                        self._task_results[task.id] = error_result
                        
                        # Remove agent from active list
                        active_agents.pop(agent.id, None)
                    
                except Exception as e:
                    logger.error(
                        "Failed to spawn agent for task",
                        task_id=str(task.id),
                        task_name=task.name,
                        error=str(e),
                    )
                    await self.task_manager.fail_task(task.id, str(e))
                    
                    # Create error task result
                    error_result = TaskResult(
                        task_id=task.id,
                        agent_id=uuid4(),
                        success=False,
                    )
                    error_result.add_error(f"Failed to spawn agent: {str(e)}")
                    self._task_results[task.id] = error_result
            
            # Wait for some tasks to complete
            if active_agents:
                await asyncio.sleep(1)  # Poll interval
                
                # Check agent status
                completed_in_round = []
                for agent_id, agent in list(active_agents.items()):
                    status = await agent.report_status()
                    
                    if status["status"] == "idle" and status["current_task"] is None:
                        # Task completed
                        task_id = UUID(status.get("last_task_id", ""))
                        if task_id:
                            artifacts = [UUID(aid) for aid in status.get("produced_artifacts", [])]
                            await self.task_manager.complete_task(task_id, artifacts)
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
        
        response = await self.claude_client.create_message(
            model=ClaudeModel.OPUS,  # Use OPUS for all meta-agent tasks
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2048,
        )
        
        try:
            specification = json.loads(response.content[0].text)
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
        
        # Use Claude to aggregate progress
        prompt = PROGRESS_AGGREGATION_PROMPT.render(
            active_tasks_json=json.dumps([t.model_dump() for t in active_tasks], indent=2),
            completed_tasks_json=json.dumps([t.model_dump() for t in completed_tasks], indent=2),
            failed_tasks_json=json.dumps([t.model_dump() for t in failed_tasks], indent=2),
            project_summary=self._active_project.get("project_summary", "") if self._active_project else "",
        )
        
        response = await self.claude_client.create_message(
            model=ClaudeModel.HAIKU,  # Use fast model for progress updates
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1024,
        )
        
        try:
            aggregated = json.loads(response.content[0].text)
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
        
        response = await self.claude_client.create_message(
            model=ClaudeModel.SONNET,
            messages=[{"role": "user", "content": analysis_prompt}],
            temperature=0.3,
            max_tokens=1024,
        )
        
        try:
            analysis = json.loads(response.content[0].text)
            
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
    
    async def coordinate_execution(self, tasks: List[Task], context: TaskContext) -> Dict[UUID, TaskResult]:
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
            Dictionary mapping task IDs to task results
        """
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
        
        return task_results
    
    async def aggregate_results(self, task_results: Dict[UUID, TaskResult]) -> ProjectResult:
        """Aggregate all task results into a final project result.
        
        Combines all artifacts and metrics into a cohesive result that
        can be presented to the user.
        
        Args:
            task_results: Dictionary mapping task IDs to TaskResults
            
        Returns:
            Aggregated project result
        """
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
        
        return ProjectResult(
            artifacts=all_artifacts,
            execution_time=execution_time,
            tasks_completed=completed,
            tasks_failed=failed,
            success_rate=completed / total if total > 0 else 0,
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
        # Use Claude to generate a short project name
        prompt = f"""Generate a SHORT project name (1-2 words max) for this request:
"{user_request}"

Rules:
- Use only lowercase letters and underscores
- Maximum 2 words connected by underscore
- Be descriptive but concise
- Focus on the main output/goal

Examples:
- "Create a hello world script" -> "hello_world"
- "Build a calculator with add and subtract" -> "calculator"
- "Make a web scraper for Amazon" -> "amazon_scraper"
- "Generate fibonacci sequence" -> "fibonacci"

Return ONLY the project name, nothing else."""
        
        try:
            response = await self.claude_client.create_message(
                model=ClaudeModel.HAIKU,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=50,
            )
            
            # Clean the response
            import re
            project_name = response.content[0].text.strip().lower()
            # Remove quotes if present
            project_name = project_name.strip('"').strip("'")
            # Ensure valid characters
            project_name = re.sub(r'[^\w]+', '_', project_name)
            project_name = project_name.strip('_')
            
            # Limit to 2 words
            words = project_name.split('_')[:2]
            project_name = '_'.join(words)
            
            # Fallback if empty
            if not project_name:
                project_name = "project"
                
            return project_name
            
        except Exception as e:
            logger.warning(f"Failed to generate project name: {e}")
            # Fallback: extract first meaningful word
            import re
            words = re.findall(r'\b\w+\b', user_request.lower())
            # Skip common words
            skip_words = {'create', 'make', 'build', 'write', 'generate', 'a', 'an', 'the', 'that', 'with'}
            meaningful_words = [w for w in words if w not in skip_words][:2]
            if meaningful_words:
                return '_'.join(meaningful_words)
            return "project"
    
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
        
        # Close Claude client
        await self.claude_client.close()
        
        # Unregister from communication
        await self.communication_hub.unregister_agent(self.id)
        
        logger.info("MetaAgent shutdown complete")