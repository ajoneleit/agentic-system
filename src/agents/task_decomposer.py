"""Task decomposition and dependency analysis module.

This module provides the TaskDecomposer class that handles breaking down
user requests into executable tasks and analyzing their dependencies.
"""

import asyncio
import json
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

from structlog import get_logger

from src.core.interfaces import Task, TaskPriority, TaskStatus
from src.core.result import Result
from src.core.exceptions import TaskDecompositionError
from src.prompts.task_decomposition import get_task_decomposition_prompt

logger = get_logger(__name__)


class TaskDecomposer:
    """Handles task decomposition and dependency analysis."""
    
    def __init__(self, openai_client=None):
        """Initialize the task decomposer.
        
        Args:
            openai_client: OpenAI client for task analysis
        """
        self.openai_client = openai_client
        self._decomposition_cache: Dict[str, List[Task]] = {}
        
    async def decompose_request(self, user_prompt: str, project_id: str) -> Result[List[Task]]:
        """Decompose a user request into executable tasks.
        
        Args:
            user_prompt: The user's request to decompose
            project_id: The project identifier
            
        Returns:
            Result containing list of tasks or error
        """
        try:
            # Check cache first
            if user_prompt in self._decomposition_cache:
                logger.info("Using cached decomposition", prompt_hash=hash(user_prompt))
                return Result.success(self._decomposition_cache[user_prompt])
            
            # Query AI for task analysis
            analysis_result = await self._query_ai_for_analysis(user_prompt)
            if analysis_result.is_failure():
                return Result.failure(analysis_result.error)
                
            # Parse the analysis response
            parsing_result = await self._parse_task_analysis(analysis_result.value)
            if parsing_result.is_failure():
                return Result.failure(parsing_result.error)
                
            # Create task objects
            tasks_result = await self._create_task_objects(parsing_result.value, project_id)
            if tasks_result.is_failure():
                return Result.failure(tasks_result.error)
                
            # Resolve dependencies
            final_tasks = await self._resolve_task_dependencies(tasks_result.value)
            
            # Cache the result
            self._decomposition_cache[user_prompt] = final_tasks
            
            logger.info(
                "Task decomposition completed", 
                task_count=len(final_tasks),
                project_id=project_id
            )
            
            return Result.success(final_tasks)
            
        except Exception as e:
            logger.error("Task decomposition failed", error=str(e), exc_info=True)
            return Result.failure(TaskDecompositionError(f"Failed to decompose request: {str(e)}"))
    
    async def _query_ai_for_analysis(self, prompt: str) -> Result[str]:
        """Query AI for task analysis.
        
        Args:
            prompt: The user prompt to analyze
            
        Returns:
            Result containing AI analysis or error
        """
        try:
            if not self.openai_client:
                return Result.failure(TaskDecompositionError("OpenAI client not configured"))
                
            decomposition_prompt = get_task_decomposition_prompt(prompt)
            
            response = await self.openai_client.create_chat_completion(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": decomposition_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            if not response or not response.choices:
                return Result.failure(TaskDecompositionError("Empty response from AI"))
                
            return Result.success(response.choices[0].message.content)
            
        except Exception as e:
            logger.error("AI query failed", error=str(e))
            return Result.failure(TaskDecompositionError(f"AI query failed: {str(e)}"))
    
    async def _parse_task_analysis(self, response: str) -> Result[Dict]:
        """Parse AI response into structured data.
        
        Args:
            response: Raw AI response
            
        Returns:
            Result containing parsed analysis or error
        """
        try:
            # Extract JSON from response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                return Result.failure(TaskDecompositionError("No JSON found in response"))
                
            json_str = response[json_start:json_end]
            analysis = json.loads(json_str)
            
            # Validate required fields
            required_fields = ['tasks', 'dependencies', 'complexity_analysis']
            for field in required_fields:
                if field not in analysis:
                    return Result.failure(TaskDecompositionError(f"Missing required field: {field}"))
            
            return Result.success(analysis)
            
        except json.JSONDecodeError as e:
            logger.error("JSON parsing failed", error=str(e))
            return Result.failure(TaskDecompositionError(f"Failed to parse JSON: {str(e)}"))
        except Exception as e:
            logger.error("Response parsing failed", error=str(e))
            return Result.failure(TaskDecompositionError(f"Failed to parse response: {str(e)}"))
    
    async def _create_task_objects(self, analysis: Dict, project_id: str) -> Result[List[Task]]:
        """Convert analysis into Task objects.
        
        Args:
            analysis: Parsed analysis dictionary
            project_id: The project identifier
            
        Returns:
            Result containing list of Task objects or error
        """
        try:
            tasks = []
            
            for task_data in analysis['tasks']:
                task = Task(
                    id=uuid4(),
                    project_id=project_id,
                    name=task_data.get('name', ''),
                    description=task_data.get('description', ''),
                    type=task_data.get('type', 'general'),
                    priority=self._parse_priority(task_data.get('priority', 'medium')),
                    status=TaskStatus.PENDING,
                    dependencies=task_data.get('dependencies', []),
                    estimated_duration=task_data.get('estimated_duration', 300),
                    metadata=task_data.get('metadata', {})
                )
                tasks.append(task)
            
            return Result.success(tasks)
            
        except Exception as e:
            logger.error("Task creation failed", error=str(e))
            return Result.failure(TaskDecompositionError(f"Failed to create tasks: {str(e)}"))
    
    async def _resolve_task_dependencies(self, tasks: List[Task]) -> List[Task]:
        """Resolve and validate task dependencies.
        
        Args:
            tasks: List of tasks to resolve dependencies for
            
        Returns:
            List of tasks with resolved dependencies
        """
        try:
            # Create mapping of task names to IDs
            name_to_id = {task.name: task.id for task in tasks}
            
            # Resolve string dependencies to UUIDs
            for task in tasks:
                resolved_deps = []
                for dep_name in task.dependencies:
                    if dep_name in name_to_id:
                        resolved_deps.append(name_to_id[dep_name])
                    else:
                        logger.warning(
                            "Dependency not found", 
                            task_name=task.name, 
                            dependency=dep_name
                        )
                
                task.dependencies = resolved_deps
            
            # Validate no circular dependencies
            self._validate_dependencies(tasks)
            
            return tasks
            
        except Exception as e:
            logger.error("Dependency resolution failed", error=str(e))
            return tasks  # Return original tasks if resolution fails
    
    def _validate_dependencies(self, tasks: List[Task]) -> None:
        """Validate that there are no circular dependencies.
        
        Args:
            tasks: List of tasks to validate
            
        Raises:
            TaskDecompositionError: If circular dependencies are found
        """
        task_map = {task.id: task for task in tasks}
        visited = set()
        rec_stack = set()
        
        def has_cycle(task_id: UUID) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)
            
            task = task_map.get(task_id)
            if task:
                for dep_id in task.dependencies:
                    if dep_id not in visited:
                        if has_cycle(dep_id):
                            return True
                    elif dep_id in rec_stack:
                        return True
            
            rec_stack.remove(task_id)
            return False
        
        for task in tasks:
            if task.id not in visited:
                if has_cycle(task.id):
                    raise TaskDecompositionError(
                        f"Circular dependency detected involving task: {task.name}"
                    )
    
    def _parse_priority(self, priority_str: str) -> TaskPriority:
        """Parse priority string into TaskPriority enum.
        
        Args:
            priority_str: Priority as string
            
        Returns:
            TaskPriority enum value
        """
        priority_map = {
            'low': TaskPriority.LOW,
            'medium': TaskPriority.MEDIUM,
            'high': TaskPriority.HIGH,
            'critical': TaskPriority.CRITICAL
        }
        
        return priority_map.get(priority_str.lower(), TaskPriority.MEDIUM)
    
    async def analyze_dependencies(self, tasks: List[Task]) -> Dict[str, List[str]]:
        """Analyze dependencies between tasks.
        
        Args:
            tasks: List of tasks to analyze
            
        Returns:
            Dictionary mapping task names to their dependencies
        """
        dependency_map = {}
        task_map = {task.id: task for task in tasks}
        
        for task in tasks:
            deps = []
            for dep_id in task.dependencies:
                if dep_id in task_map:
                    deps.append(task_map[dep_id].name)
            dependency_map[task.name] = deps
        
        return dependency_map
    
    async def validate_dependencies(self, dependencies: Dict[str, List[str]]) -> bool:
        """Validate that dependencies are satisfiable.
        
        Args:
            dependencies: Dictionary of task dependencies
            
        Returns:
            True if dependencies are valid, False otherwise
        """
        try:
            # Check for self-dependencies
            for task_name, deps in dependencies.items():
                if task_name in deps:
                    logger.error("Self-dependency detected", task=task_name)
                    return False
            
            # Check for circular dependencies using DFS
            visited = set()
            rec_stack = set()
            
            def has_cycle(task_name: str) -> bool:
                visited.add(task_name)
                rec_stack.add(task_name)
                
                for dep in dependencies.get(task_name, []):
                    if dep not in visited:
                        if has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        return True
                
                rec_stack.remove(task_name)
                return False
            
            for task_name in dependencies:
                if task_name not in visited:
                    if has_cycle(task_name):
                        logger.error("Circular dependency detected", task=task_name)
                        return False
            
            return True
            
        except Exception as e:
            logger.error("Dependency validation failed", error=str(e))
            return False
    
    def clear_cache(self) -> None:
        """Clear the decomposition cache."""
        self._decomposition_cache.clear()
        logger.info("Task decomposition cache cleared")