"""Extended Meta Agent with integrated verification system.

This module extends the base MetaAgent to include automatic verification
of generated code and test execution.
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Set
from uuid import UUID

from src.agents.meta_agent import MetaAgent, ProjectResult
from src.core.interfaces import Agent, AgentRole, Task, TaskContext, TaskStatus
from src.core.exceptions import TaskError
from src.core.task_result import TaskResult
from src.utils.app_logging import get_logger
from src.verification.integration import (
    VerificationIntegration,
    TaskVerificationResult,
    ProjectVerificationResult,
)
from src.verification.verifier_base import VerificationConfig


logger = get_logger(__name__)


class MetaAgentWithVerification(MetaAgent):
    """Meta Agent with integrated verification system.
    
    This extends the base MetaAgent to automatically verify generated code
    and run tests as part of the task execution flow.
    """
    
    def __init__(
        self,
        artifact_storage_path: Optional[Path] = None,
        verification_config: Optional[VerificationConfig] = None
    ):
        """Initialize Meta Agent with verification.
        
        Args:
            artifact_storage_path: Path for artifact storage
            verification_config: Configuration for verification
        """
        super().__init__(artifact_storage_path)
        
        # Initialize verification
        self.verification_config = verification_config or VerificationConfig()
        self.verification_integration: Optional[VerificationIntegration] = None
        self._verification_results: Dict[UUID, TaskVerificationResult] = {}
        
        # Enable verification by default
        self.enable_verification = True
        self.enable_auto_repair = True
        self.max_repair_attempts = 3
    
    async def _initialize_verification(self) -> None:
        """Initialize the verification integration."""
        if not self.verification_integration:
            self.verification_integration = VerificationIntegration(
                artifact_manager=self.artifact_manager,
                task_manager=self.task_manager,
                config=self.verification_config
            )
            logger.info("Verification system initialized")
    
    async def _execute_tasks(
        self,
        tasks: List[Task],
        context: TaskContext
    ) -> None:
        """Execute tasks with verification.
        
        This overrides the parent method to add verification after each task.
        
        Args:
            tasks: Tasks to execute
            context: Execution context
        """
        # Initialize verification if needed
        if self.enable_verification:
            await self._initialize_verification()
        
        completed_tasks: Set[UUID] = set()
        active_agents: Dict[UUID, Agent] = {}
        repair_attempts: Dict[UUID, int] = {}
        
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
            
            # Process ready tasks
            for task in ready_tasks:
                try:
                    # Execute task normally
                    agent = await self.spawn_agent(task.required_role or AgentRole.CORE_LOGIC, context)
                    active_agents[agent.id] = agent
                    
                    await self.task_manager.start_task(task.id)
                    
                    # Execute task
                    task_result = await agent.execute_task(task, context)
                    self._task_results[task.id] = task_result
                    
                    # Verify if enabled and task succeeded
                    if self.enable_verification and task_result.success:
                        verification_passed = await self._verify_task_with_repair(
                            task, task_result, repair_attempts
                        )
                        
                        if verification_passed:
                            await self.task_manager.complete_task(task.id, task_result.artifacts)
                            completed_tasks.add(task.id)
                        else:
                            # Verification failed and repair exhausted
                            await self.task_manager.fail_task(
                                task.id,
                                "Verification failed after repair attempts"
                            )
                            completed_tasks.add(task.id)
                    else:
                        # No verification or task failed
                        if task_result.success:
                            await self.task_manager.complete_task(task.id, task_result.artifacts)
                        else:
                            error_msg = "; ".join(task_result.errors) if task_result.errors else "Task failed"
                            await self.task_manager.fail_task(task.id, error_msg)
                        completed_tasks.add(task.id)
                    
                    # Remove agent
                    active_agents.pop(agent.id, None)
                    
                except Exception as e:
                    logger.error(
                        "Task execution failed",
                        task_id=str(task.id),
                        error=str(e),
                        exc_info=True,
                    )
                    await self.task_manager.fail_task(task.id, str(e))
                    completed_tasks.add(task.id)
                    
                    # Create error result
                    if agent:
                        error_result = TaskResult(
                            task_id=task.id,
                            agent_id=agent.id,
                            success=False,
                        )
                        error_result.add_error(str(e))
                        self._task_results[task.id] = error_result
                        active_agents.pop(agent.id, None)
            
            # Small delay to prevent busy loop
            if not ready_tasks:
                await asyncio.sleep(0.1)
    
    async def _verify_task_with_repair(
        self,
        task: Task,
        task_result: TaskResult,
        repair_attempts: Dict[UUID, int]
    ) -> bool:
        """Verify task and attempt repairs if needed.
        
        Args:
            task: The task to verify
            task_result: The task execution result
            repair_attempts: Track repair attempts per task
            
        Returns:
            True if verification passed (possibly after repairs)
        """
        if not self.verification_integration:
            return True
        
        attempts = repair_attempts.get(task.id, 0)
        
        while attempts < self.max_repair_attempts:
            # Run verification
            logger.info(f"Verifying task {task.id}: {task.name}")
            verification_result = await self.verification_integration.verify_task_artifacts(task)
            self._verification_results[task.id] = verification_result
            
            if verification_result.success:
                logger.info(f"Task {task.id} passed verification")
                return True
            
            # Verification failed
            logger.warning(
                f"Task {task.id} failed verification",
                syntax_errors=verification_result.has_syntax_errors,
                compilation_errors=verification_result.has_compilation_errors,
                test_failures=verification_result.has_test_failures,
            )
            
            if not self.enable_auto_repair or attempts >= self.max_repair_attempts - 1:
                return False
            
            # Increment counter BEFORE repair execution
            attempts += 1
            repair_attempts[task.id] = attempts
            
            # Generate and execute repair tasks
            logger.info(f"Attempting repair for task {task.id} (attempt {attempts})")
            repair_tasks = await self.verification_integration.generate_repair_tasks(
                verification_result
            )
            
            if repair_tasks:
                # Add repair tasks
                await self.task_manager.add_tasks(repair_tasks)
                
                # Execute repair tasks
                for repair_task in repair_tasks:
                    # Execute repair inline
                    agent = await self.spawn_agent(
                        repair_task.required_role or AgentRole.CODE_GENERATOR,
                        self.context
                    )
                    
                    repair_result = await agent.execute_task(repair_task, self.context)
                    
                    if repair_result.success:
                        # Update original task artifacts with repaired versions
                        task.artifacts.extend(repair_result.artifacts)
                        task_result.artifacts.extend(repair_result.artifacts)
                    else:
                        logger.error(f"Repair task failed for {task.id}")
                        return False
        
        return False
    
    async def process_request(self, user_request: str) -> ProjectResult:
        """Process user request with verification.
        
        Args:
            user_request: Natural language request from user
            
        Returns:
            Project execution result with verification status
        """
        result = await super().process_request(user_request)
        
        # Add verification results to metadata
        if self.enable_verification and self._verification_results:
            verification_summary = {
                "total_tasks_verified": len(self._verification_results),
                "verification_passed": sum(
                    1 for v in self._verification_results.values() if v.success
                ),
                "syntax_errors": sum(
                    1 for v in self._verification_results.values() if v.has_syntax_errors
                ),
                "compilation_errors": sum(
                    1 for v in self._verification_results.values() if v.has_compilation_errors
                ),
                "test_failures": sum(
                    1 for v in self._verification_results.values() if v.has_test_failures
                ),
            }
            result.metadata["verification_summary"] = verification_summary
            
            # Add detailed verification results
            result.metadata["verification_results"] = {
                str(task_id): {
                    "success": vr.success,
                    "total_verifications": vr.total_verifications,
                    "passed": vr.passed_verifications,
                    "failed": vr.failed_verifications,
                }
                for task_id, vr in self._verification_results.items()
            }
        
        return result
    
    def get_verification_results(self) -> Dict[UUID, TaskVerificationResult]:
        """Get all verification results.
        
        Returns:
            Dictionary of task verification results
        """
        return self._verification_results
    
    async def verify_project(self, project_id: str) -> ProjectVerificationResult:
        """Verify an entire project.
        
        Args:
            project_id: The project to verify
            
        Returns:
            Project verification result
        """
        if not self.verification_integration:
            await self._initialize_verification()
        
        return await self.verification_integration.verify_project(project_id)