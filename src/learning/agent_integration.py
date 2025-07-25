"""
Integration layer between the Prompt Evolution System and existing AI agents.

This module provides seamless integration between the prompt evolution system
and the existing agent architecture, enabling automatic prompt tracking,
evolution, and feedback collection.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from src.core.interfaces import Agent, Task, TaskContext
from src.learning.prompt_evolution import PromptEvolutionSystem, PromptTemplate


logger = logging.getLogger(__name__)


class AgentPromptIntegration:
    """
    Integration layer between the Prompt Evolution System and existing AI agents.
    
    This class wraps agent execution to automatically track prompt performance,
    collect feedback, and trigger evolution when needed.
    """
    
    def __init__(self, prompt_evolution_system: PromptEvolutionSystem, agent_manager):
        """Initialize the integration layer.
        
        Args:
            prompt_evolution_system: The prompt evolution system instance
            agent_manager: The existing agent manager for task execution
        """
        self.evolution_system = prompt_evolution_system
        self.agent_manager = agent_manager
        self.logger = logging.getLogger(__name__)
    
    async def execute_with_evolution(self, agent_id: str, task_type: str, 
                                   template_id: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute agent task with prompt evolution tracking.
        
        This method wraps the standard agent execution to provide:
        - Automatic prompt tracking
        - Performance measurement
        - Error collection
        - Evolution trigger points
        
        Args:
            agent_id: ID of the agent to execute the task
            task_type: Type of task being executed
            template_id: ID of the prompt template to use
            variables: Variables to substitute in the prompt template
            
        Returns:
            Task execution result with evolution tracking metadata
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Get the current best template
            template = await self._get_active_template(template_id)
            if not template:
                raise ValueError(f"Template {template_id} not found")
            
            # Render prompt with variables
            prompt_content = self._render_prompt(template.template_content, variables)
            
            # Execute the agent task
            result = await self.agent_manager.execute_task(agent_id, prompt_content, task_type)
            
            # Calculate execution metrics
            execution_time = asyncio.get_event_loop().time() - start_time
            success = result.get("success", False)
            error_details = result.get("error") if not success else None
            
            # Record execution in evolution system
            execution_id = await self.evolution_system.record_execution(
                template_id=template_id,
                prompt_content=prompt_content,
                task_type=task_type,
                success=success,
                execution_time=execution_time,
                performance_metrics=result.get("metrics", {}),
                error_details=error_details
            )
            
            # Add evolution tracking to result
            result["evolution_tracking"] = {
                "execution_id": execution_id,
                "template_id": template_id,
                "template_version": template.version
            }
            
            return result
            
        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            
            # Record failed execution
            await self.evolution_system.record_execution(
                template_id=template_id,
                prompt_content="",
                task_type=task_type,
                success=False,
                execution_time=execution_time,
                error_details=str(e)
            )
            
            raise e
    
    async def provide_feedback(self, execution_id: str, feedback_data: Dict[str, Any]) -> bool:
        """
        Provide feedback for a specific execution to improve future prompts.
        
        Args:
            execution_id: ID of the execution to provide feedback for
            feedback_data: Feedback data including:
                - score: Overall quality score (1-5)
                - improvement_areas: List of areas needing improvement
                - positive_aspects: List of what worked well
                - specific_comments: Detailed feedback text
                
        Returns:
            True if feedback was successfully integrated
        """
        return await self.evolution_system.integrate_learning(execution_id, feedback_data)
    
    async def get_performance_insights(self, time_window_hours: int = 24) -> Dict[str, Any]:
        """
        Get performance insights for the agents.
        
        Args:
            time_window_hours: Time window to analyze (default: 24 hours)
            
        Returns:
            Performance analysis results
        """
        return await self.evolution_system.analyze_performance_patterns(time_window_hours)
    
    async def trigger_evolution_cycle(self) -> List[str]:
        """
        Manually trigger an evolution cycle for templates.
        
        Returns:
            List of newly evolved template IDs
        """
        return await self.evolution_system.evolve_templates()
    
    async def get_template_recommendations(self, task_type: str) -> Dict[str, Any]:
        """
        Get template recommendations for a specific task type.
        
        Args:
            task_type: Type of task to get recommendations for
            
        Returns:
            Dictionary with recommended templates and their performance metrics
        """
        try:
            # Get all active templates for this task type
            templates = self.evolution_system.db_session.query(PromptTemplate).filter_by(
                is_active=True
            ).all()
            
            # Filter templates that have been used for this task type
            task_templates = []
            for template in templates:
                # Check if template has been used for this task type
                executions = self.evolution_system.db_session.query(
                    self.evolution_system.PromptExecution
                ).filter_by(
                    template_id=template.template_id,
                    task_type=task_type
                ).limit(5).all()
                
                if executions:
                    metrics = await self.evolution_system.get_template_metrics(template.template_id)
                    task_templates.append({
                        "template_id": template.template_id,
                        "template_name": template.template_id,
                        "metrics": metrics,
                        "recent_usage": len(executions)
                    })
            
            # Sort by performance score
            task_templates.sort(key=lambda x: x["metrics"].success_rate, reverse=True)
            
            return {
                "recommended_templates": task_templates[:5],  # Top 5 recommendations
                "task_type": task_type,
                "total_templates_available": len(task_templates)
            }
            
        except Exception as e:
            self.logger.error(f"Error getting template recommendations: {str(e)}")
            return {"error": str(e)}
    
    async def create_template_from_success(self, execution_id: str, 
                                         template_name: str,
                                         category: str = "user_generated") -> Optional[str]:
        """
        Create a new template based on a successful execution.
        
        Args:
            execution_id: ID of successful execution to base template on
            template_name: Name for the new template
            category: Category for the template
            
        Returns:
            ID of newly created template or None if creation failed
        """
        try:
            # Get the execution record
            execution = self.evolution_system.db_session.query(
                self.evolution_system.PromptExecution
            ).filter_by(execution_id=execution_id).first()
            
            if not execution or not execution.success:
                self.logger.warning(f"Execution {execution_id} not found or was not successful")
                return None
            
            # Create new template
            new_template = PromptTemplate(
                template_id=f"{template_name}_{int(asyncio.get_event_loop().time())}",
                template_content=execution.prompt_content,
                variables=[],  # Extract variables if needed
                category=category,
                version=1,
                is_active=True
            )
            
            self.evolution_system.db_session.add(new_template)
            self.evolution_system.db_session.commit()
            
            self.logger.info(f"Created new template {new_template.template_id} from successful execution")
            return new_template.template_id
            
        except Exception as e:
            self.logger.error(f"Error creating template from success: {str(e)}")
            return None
    
    # Private helper methods
    
    def _render_prompt(self, template_content: str, variables: Dict[str, Any]) -> str:
        """
        Render prompt template with provided variables.
        
        Args:
            template_content: Template content with placeholders
            variables: Variables to substitute
            
        Returns:
            Rendered prompt content
        """
        try:
            return template_content.format(**variables)
        except KeyError as e:
            self.logger.error(f"Missing variable {e} for prompt template")
            raise ValueError(f"Missing required variable: {e}")
    
    async def _get_active_template(self, template_id: str) -> Optional[PromptTemplate]:
        """
        Get the currently active version of a template.
        
        Args:
            template_id: ID of template to retrieve
            
        Returns:
            Active template instance or None if not found
        """
        return self.evolution_system.db_session.query(PromptTemplate).filter_by(
            template_id=template_id, is_active=True
        ).first()


class EnhancedAgent:
    """
    Enhanced agent wrapper that integrates with the prompt evolution system.
    
    This class wraps existing agents to provide automatic prompt evolution
    capabilities without modifying the original agent implementations.
    """
    
    def __init__(self, base_agent: Agent, integration: AgentPromptIntegration):
        """Initialize enhanced agent.
        
        Args:
            base_agent: The base agent to enhance
            integration: Prompt evolution integration instance
        """
        self.base_agent = base_agent
        self.integration = integration
        self.logger = logging.getLogger(__name__)
        
        # Copy agent properties
        self.id = base_agent.id
        self.role = base_agent.role
        self.status = base_agent.status
    
    async def execute_task(self, task: Task, context: TaskContext) -> "TaskResult":
        """
        Execute task with prompt evolution tracking.
        
        Args:
            task: Task to execute
            context: Task execution context
            
        Returns:
            TaskResult with evolution tracking
        """
        # Determine appropriate template for this task
        template_id = self._get_template_for_task(task)
        
        # Prepare variables for template rendering
        variables = self._extract_template_variables(task, context)
        
        # Execute with evolution tracking
        result = await self.integration.execute_with_evolution(
            agent_id=str(self.id),
            task_type=task.name,
            template_id=template_id,
            variables=variables
        )
        
        # Delegate to base agent for actual execution
        base_result = await self.base_agent.execute_task(task, context)
        
        # Merge results
        base_result.metadata = {
            **base_result.metadata,
            **result.get("evolution_tracking", {})
        }
        
        return base_result
    
    async def initialize(self, context: TaskContext) -> None:
        """Initialize the enhanced agent."""
        await self.base_agent.initialize(context)
    
    async def collaborate(self, other_agent: Agent, message: Dict[str, Any]) -> Dict[str, Any]:
        """Collaborate with another agent."""
        return await self.base_agent.collaborate(other_agent, message)
    
    async def shutdown(self) -> None:
        """Shutdown the enhanced agent."""
        await self.base_agent.shutdown()
    
    def _get_template_for_task(self, task: Task) -> str:
        """
        Determine the appropriate template ID for a task.
        
        Args:
            task: Task to get template for
            
        Returns:
            Template ID to use
        """
        # Simple mapping based on task type/role
        role_templates = {
            "core_logic": "code_generation_template",
            "testing": "test_generation_template", 
            "documentation": "documentation_template",
            "optimization": "optimization_template"
        }
        
        return role_templates.get(self.role.value, "default_template")
    
    def _extract_template_variables(self, task: Task, context: TaskContext) -> Dict[str, Any]:
        """
        Extract variables for template rendering from task and context.
        
        Args:
            task: Task being executed
            context: Task execution context
            
        Returns:
            Variables dictionary for template rendering
        """
        return {
            "task_name": task.name,
            "task_description": task.description,
            "task_priority": task.priority.value,
            "project_root": str(context.project_root),
            "agent_role": self.role.value,
            "task_id": str(task.id)
        }


class EvolutionMetricsCollector:
    """
    Collector for evolution system metrics and insights.
    
    Provides methods to gather and analyze metrics across the entire
    prompt evolution system for monitoring and reporting.
    """
    
    def __init__(self, evolution_system: PromptEvolutionSystem):
        """Initialize metrics collector.
        
        Args:
            evolution_system: The prompt evolution system to collect metrics from
        """
        self.evolution_system = evolution_system
        self.logger = logging.getLogger(__name__)
    
    async def collect_system_metrics(self) -> Dict[str, Any]:
        """
        Collect comprehensive system metrics.
        
        Returns:
            Dictionary with system-wide metrics
        """
        try:
            # Get database statistics
            db_session = self.evolution_system.db_session
            
            total_templates = db_session.query(PromptTemplate).count()
            active_templates = db_session.query(PromptTemplate).filter_by(is_active=True).count()
            total_executions = db_session.query(
                self.evolution_system.PromptExecution
            ).count()
            
            # Get recent performance data
            recent_patterns = await self.evolution_system.analyze_performance_patterns(24)
            
            # Calculate evolution statistics
            evolution_history = db_session.query(
                self.evolution_system.EvolutionHistory
            ).count()
            
            return {
                "templates": {
                    "total": total_templates,
                    "active": active_templates,
                    "inactive": total_templates - active_templates
                },
                "executions": {
                    "total": total_executions,
                    "recent_24h": len(recent_patterns.get("overall_metrics", {}))
                },
                "evolution": {
                    "total_evolutions": evolution_history,
                    "recent_patterns": recent_patterns
                },
                "timestamp": asyncio.get_event_loop().time()
            }
            
        except Exception as e:
            self.logger.error(f"Error collecting system metrics: {str(e)}")
            return {"error": str(e)}
    
    async def get_top_performing_templates(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top performing templates by success rate.
        
        Args:
            limit: Maximum number of templates to return
            
        Returns:
            List of top performing templates with metrics
        """
        try:
            templates = self.evolution_system.db_session.query(PromptTemplate).filter_by(
                is_active=True
            ).order_by(PromptTemplate.performance_score.desc()).limit(limit).all()
            
            results = []
            for template in templates:
                metrics = await self.evolution_system.get_template_metrics(template.template_id)
                results.append({
                    "template_id": template.template_id,
                    "category": template.category,
                    "version": template.version,
                    "performance_score": template.performance_score,
                    "usage_count": template.usage_count,
                    "metrics": metrics
                })
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error getting top performing templates: {str(e)}")
            return []
    
    async def get_evolution_trends(self, days: int = 7) -> Dict[str, Any]:
        """
        Get evolution trends over time.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Evolution trends data
        """
        try:
            from datetime import datetime, timedelta
            
            cutoff_time = datetime.utcnow() - timedelta(days=days)
            
            # Get evolution history
            evolutions = self.evolution_system.db_session.query(
                self.evolution_system.EvolutionHistory
            ).filter(
                self.evolution_system.EvolutionHistory.created_at >= cutoff_time
            ).all()
            
            # Group by strategy
            strategy_counts = {}
            for evolution in evolutions:
                strategy = evolution.evolution_strategy
                strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
            
            # Calculate daily evolution rates
            daily_evolutions = defaultdict(int)
            for evolution in evolutions:
                day = evolution.created_at.date()
                daily_evolutions[day] += 1
            
            return {
                "total_evolutions": len(evolutions),
                "strategy_breakdown": strategy_counts,
                "daily_evolutions": dict(daily_evolutions),
                "average_daily_rate": len(evolutions) / days if days > 0 else 0
            }
            
        except Exception as e:
            self.logger.error(f"Error getting evolution trends: {str(e)}")
            return {"error": str(e)}