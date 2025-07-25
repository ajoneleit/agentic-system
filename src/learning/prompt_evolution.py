"""
Prompt Evolution System powered by OpenAI o3.

This module implements the Prompt Evolution System as specified in the system plan,
providing autonomous prompt refinement, performance analysis, template evolution,
and learning integration capabilities.
"""

import asyncio
import hashlib
import json
import logging
import statistics
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    JSON,
    String,
    Text,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from src.clients.openai_client import OpenAIClient, OpenAIModel

Base = declarative_base()

logger = logging.getLogger(__name__)


class PromptTemplate(Base):
    """Database model for prompt templates."""
    
    __tablename__ = "prompt_templates"
    
    id = Column(Integer, primary_key=True)
    template_id = Column(String(255), unique=True, index=True)
    template_content = Column(Text)
    variables = Column(JSON)
    category = Column(String(100))
    version = Column(Integer, default=1)
    parent_template_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    performance_score = Column(Float, default=0.0)
    usage_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)


class PromptExecution(Base):
    """Database model for prompt execution tracking."""
    
    __tablename__ = "prompt_executions"
    
    id = Column(Integer, primary_key=True)
    execution_id = Column(String(255), unique=True, index=True)
    template_id = Column(String(255), index=True)
    prompt_content = Column(Text)
    task_type = Column(String(100))
    success = Column(Boolean)
    performance_metrics = Column(JSON)
    execution_time = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    feedback_score = Column(Float, nullable=True)
    error_details = Column(Text, nullable=True)


class EvolutionHistory(Base):
    """Database model for tracking evolution history."""
    
    __tablename__ = "evolution_history"
    
    id = Column(Integer, primary_key=True)
    evolution_id = Column(String(255), unique=True, index=True)
    original_template_id = Column(String(255))
    evolved_template_id = Column(String(255))
    evolution_strategy = Column(String(100))
    improvement_metrics = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


@dataclass
class PromptMetrics:
    """Metrics for evaluating prompt performance."""
    
    success_rate: float
    avg_execution_time: float
    avg_feedback_score: float
    usage_frequency: int
    error_patterns: List[str]
    improvement_potential: float


@dataclass
class EvolutionStrategy:
    """Strategy for prompt evolution."""
    
    name: str
    description: str
    weight: float
    mutation_rate: float


class PromptEvolutionSystem:
    """
    Prompt Evolution System powered by OpenAI o3.
    
    Continuously improves prompt quality through autonomous refinement,
    performance analysis, template evolution, and learning integration.
    """
    
    def __init__(self, db_session, openai_client: OpenAIClient, config: Dict[str, Any]):
        """Initialize the Prompt Evolution System.
        
        Args:
            db_session: SQLAlchemy database session
            openai_client: OpenAI client instance
            config: Configuration dictionary
        """
        self.db_session = db_session
        self.openai_client = openai_client
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Evolution strategies with different approaches
        self.evolution_strategies = [
            EvolutionStrategy("clarity_enhancement", "Improve prompt clarity and specificity", 0.3, 0.2),
            EvolutionStrategy("context_optimization", "Optimize context and examples", 0.25, 0.15),
            EvolutionStrategy("structure_refinement", "Refine prompt structure and flow", 0.2, 0.1),
            EvolutionStrategy("performance_tuning", "Tune for specific performance metrics", 0.25, 0.3)
        ]
        
        # Performance tracking
        self.performance_history = defaultdict(lambda: deque(maxlen=100))
        self.template_metrics_cache = {}
        self.cache_ttl = timedelta(minutes=30)
        self.last_cache_update = {}
        
        # Learning parameters
        self.learning_rate = config.get("learning_rate", 0.1)
        self.exploration_rate = config.get("exploration_rate", 0.2)
        self.min_samples_for_evolution = config.get("min_samples_for_evolution", 10)
    
    async def autonomous_prompt_refinement(self, template_id: str) -> Optional[str]:
        """
        Continuously improves prompt quality and effectiveness through autonomous refinement.
        
        Args:
            template_id: ID of template to refine
            
        Returns:
            ID of new refined template or None if no refinement needed
        """
        try:
            # Get current template and its performance metrics
            template = self.db_session.query(PromptTemplate).filter_by(
                template_id=template_id, is_active=True
            ).first()
            
            if not template:
                self.logger.warning(f"Template {template_id} not found for refinement")
                return None
                
            metrics = await self.get_template_metrics(template_id)
            
            # Check if refinement is needed
            if not self._should_refine_template(metrics):
                return None
                
            # Select evolution strategy based on current performance gaps
            strategy = self._select_evolution_strategy(metrics)
            
            # Generate refined prompt using OpenAI o3
            refined_prompt = await self._generate_refined_prompt(
                template.template_content, strategy, metrics
            )
            
            if refined_prompt:
                # Create new template version
                new_template_id = await self._create_evolved_template(
                    template, refined_prompt, strategy.name
                )
                
                self.logger.info(f"Successfully refined template {template_id} -> {new_template_id}")
                return new_template_id
                
        except Exception as e:
            self.logger.error(f"Error in autonomous prompt refinement: {str(e)}")
            return None
    
    async def analyze_performance_patterns(self, time_window_hours: int = 24) -> Dict[str, Any]:
        """
        Analyzes success/failure patterns across task executions.
        
        Args:
            time_window_hours: Time window for analysis in hours
            
        Returns:
            Analysis results with patterns and recommendations
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=time_window_hours)
            
            executions = self.db_session.query(PromptExecution).filter(
                PromptExecution.created_at >= cutoff_time
            ).all()
            
            if not executions:
                return {"message": "No executions found in the specified time window"}
            
            # Analyze patterns by various dimensions
            patterns = {
                "overall_metrics": self._calculate_overall_metrics(executions),
                "template_performance": self._analyze_template_performance(executions),
                "task_type_patterns": self._analyze_task_type_patterns(executions),
                "temporal_patterns": self._analyze_temporal_patterns(executions),
                "error_patterns": self._analyze_error_patterns(executions),
                "recommendations": []
            }
            
            # Generate actionable recommendations
            patterns["recommendations"] = self._generate_recommendations(patterns)
            
            return patterns
            
        except Exception as e:
            self.logger.error(f"Error analyzing performance patterns: {str(e)}")
            return {"error": str(e)}
    
    async def evolve_templates(self, batch_size: int = 5) -> List[str]:
        """
        Develops and refines prompt templates based on empirical results.
        
        Args:
            batch_size: Number of templates to evolve in this batch
            
        Returns:
            List of newly evolved template IDs
        """
        try:
            # Get templates that need evolution
            candidates = await self._get_evolution_candidates(batch_size)
            evolved_templates = []
            
            for template_id in candidates:
                new_template_id = await self.autonomous_prompt_refinement(template_id)
                if new_template_id:
                    evolved_templates.append(new_template_id)
                    
                    # Schedule A/B testing for the new template
                    await self._schedule_ab_testing(template_id, new_template_id)
            
            self.logger.info(f"Evolved {len(evolved_templates)} templates in this batch")
            return evolved_templates
            
        except Exception as e:
            self.logger.error(f"Error in template evolution: {str(e)}")
            return []
    
    async def integrate_learning(self, execution_id: str, feedback_data: Dict[str, Any]) -> bool:
        """
        Incorporates lessons learned into future prompt generation.
        
        Args:
            execution_id: ID of the execution to provide feedback for
            feedback_data: Feedback data including score and improvement areas
            
        Returns:
            True if learning was successfully integrated
        """
        try:
            # Update execution record with feedback
            execution = self.db_session.query(PromptExecution).filter_by(
                execution_id=execution_id
            ).first()
            
            if not execution:
                self.logger.warning(f"Execution {execution_id} not found for learning integration")
                return False
            
            # Extract learning signals from feedback
            learning_signals = self._extract_learning_signals(feedback_data)
            
            # Update execution with feedback score
            execution.feedback_score = feedback_data.get("score", 0.0)
            execution.performance_metrics = {
                **(execution.performance_metrics or {}),
                **learning_signals
            }
            
            # Update template performance metrics
            await self._update_template_learning(execution.template_id, learning_signals)
            
            # Trigger evolution if significant learning opportunity is detected
            if learning_signals.get("improvement_potential", 0) > 0.3:
                await self.autonomous_prompt_refinement(execution.template_id)
            
            self.db_session.commit()
            self.logger.info(f"Successfully integrated learning from execution {execution_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error integrating learning: {str(e)}")
            self.db_session.rollback()
            return False
    
    async def get_template_metrics(self, template_id: str) -> PromptMetrics:
        """Get comprehensive metrics for a specific template.
        
        Args:
            template_id: ID of template to get metrics for
            
        Returns:
            PromptMetrics with performance data
        """
        # Check cache first
        cache_key = f"metrics_{template_id}"
        if (cache_key in self.template_metrics_cache and 
            cache_key in self.last_cache_update and
            datetime.utcnow() - self.last_cache_update[cache_key] < self.cache_ttl):
            return self.template_metrics_cache[cache_key]
        
        # Calculate metrics from database
        executions = self.db_session.query(PromptExecution).filter_by(
            template_id=template_id
        ).all()
        
        if not executions:
            return PromptMetrics(0.0, 0.0, 0.0, 0, [], 0.0)
        
        success_rate = sum(1 for e in executions if e.success) / len(executions)
        avg_execution_time = statistics.mean([e.execution_time for e in executions if e.execution_time])
        
        feedback_scores = [e.feedback_score for e in executions if e.feedback_score is not None]
        avg_feedback_score = statistics.mean(feedback_scores) if feedback_scores else 0.0
        
        error_patterns = self._extract_error_patterns(executions)
        improvement_potential = self._calculate_improvement_potential(executions)
        
        metrics = PromptMetrics(
            success_rate=success_rate,
            avg_execution_time=avg_execution_time,
            avg_feedback_score=avg_feedback_score,
            usage_frequency=len(executions),
            error_patterns=error_patterns,
            improvement_potential=improvement_potential
        )
        
        # Cache the results
        self.template_metrics_cache[cache_key] = metrics
        self.last_cache_update[cache_key] = datetime.utcnow()
        
        return metrics
    
    async def record_execution(self, template_id: str, prompt_content: str, 
                             task_type: str, success: bool, execution_time: float,
                             performance_metrics: Dict[str, Any] = None,
                             error_details: str = None) -> str:
        """Record a prompt execution for performance tracking.
        
        Args:
            template_id: ID of template used
            prompt_content: Actual prompt content used
            task_type: Type of task executed
            success: Whether execution was successful  
            execution_time: Time taken for execution
            performance_metrics: Additional performance metrics
            error_details: Error details if execution failed
            
        Returns:
            Unique execution ID
        """
        execution_id = self._generate_execution_id(template_id, prompt_content)
        
        execution = PromptExecution(
            execution_id=execution_id,
            template_id=template_id,
            prompt_content=prompt_content,
            task_type=task_type,
            success=success,
            performance_metrics=performance_metrics or {},
            execution_time=execution_time,
            error_details=error_details
        )
        
        self.db_session.add(execution)
        self.db_session.commit()
        
        # Update performance history for real-time tracking
        self.performance_history[template_id].append({
            "success": success,
            "execution_time": execution_time,
            "timestamp": datetime.utcnow()
        })
        
        # Invalidate metrics cache for this template
        cache_key = f"metrics_{template_id}"
        if cache_key in self.template_metrics_cache:
            del self.template_metrics_cache[cache_key]
            del self.last_cache_update[cache_key]
        
        return execution_id
    
    # Private helper methods
    
    def _should_refine_template(self, metrics: PromptMetrics) -> bool:
        """Determine if a template should be refined based on its metrics."""
        # Refine if success rate is below threshold
        if metrics.success_rate < self.config.get("min_success_rate", 0.8):
            return True
            
        # Refine if improvement potential is high
        if metrics.improvement_potential > self.config.get("improvement_threshold", 0.3):
            return True
            
        # Refine if feedback score is low
        if metrics.avg_feedback_score < self.config.get("min_feedback_score", 3.0):
            return True
            
        return False
    
    def _select_evolution_strategy(self, metrics: PromptMetrics) -> EvolutionStrategy:
        """Select the most appropriate evolution strategy based on current metrics."""
        # Simple strategy selection based on primary weakness
        if metrics.success_rate < 0.6:
            return next(s for s in self.evolution_strategies if s.name == "clarity_enhancement")
        elif metrics.avg_execution_time > self.config.get("max_execution_time", 10.0):
            return next(s for s in self.evolution_strategies if s.name == "performance_tuning")
        elif len(metrics.error_patterns) > 3:
            return next(s for s in self.evolution_strategies if s.name == "structure_refinement")
        else:
            return next(s for s in self.evolution_strategies if s.name == "context_optimization")
    
    async def _generate_refined_prompt(self, original_prompt: str, 
                                     strategy: EvolutionStrategy,
                                     metrics: PromptMetrics) -> Optional[str]:
        """Generate a refined prompt using OpenAI o3."""
        try:
            evolution_prompt = f"""
            You are an expert prompt engineer tasked with improving the following prompt using the "{strategy.name}" strategy.
            
            Original Prompt:
            {original_prompt}
            
            Current Performance Metrics:
            - Success Rate: {metrics.success_rate:.2f}
            - Average Execution Time: {metrics.avg_execution_time:.2f}s
            - Average Feedback Score: {metrics.avg_feedback_score:.2f}
            - Common Error Patterns: {', '.join(metrics.error_patterns[:3])}
            
            Strategy Focus: {strategy.description}
            
            Please provide an improved version of this prompt that addresses the performance issues while maintaining the original intent. Focus specifically on {strategy.description.lower()}.
            
            Return only the improved prompt without additional commentary.
            """
            
            messages = [{"role": "user", "content": evolution_prompt}]
            
            response = await self.openai_client.create_message(
                messages=messages,
                model=OpenAIModel.O3_MINI,  # Use o3-mini model as specified
                max_tokens=2000
            )
            
            return response["content"].strip()
            
        except Exception as e:
            self.logger.error(f"Error generating refined prompt: {str(e)}")
            return None
    
    async def _create_evolved_template(self, parent_template: PromptTemplate, 
                                     refined_content: str, strategy_name: str) -> str:
        """Create a new template version from evolution."""
        new_template_id = f"{parent_template.template_id}_v{parent_template.version + 1}"
        
        new_template = PromptTemplate(
            template_id=new_template_id,
            template_content=refined_content,
            variables=parent_template.variables,
            category=parent_template.category,
            version=parent_template.version + 1,
            parent_template_id=parent_template.template_id,
            is_active=False  # Start inactive for A/B testing
        )
        
        self.db_session.add(new_template)
        
        # Record evolution history
        evolution_history = EvolutionHistory(
            evolution_id=self._generate_evolution_id(parent_template.template_id, new_template_id),
            original_template_id=parent_template.template_id,
            evolved_template_id=new_template_id,
            evolution_strategy=strategy_name,
            improvement_metrics={}
        )
        
        self.db_session.add(evolution_history)
        self.db_session.commit()
        
        return new_template_id
    
    def _generate_execution_id(self, template_id: str, prompt_content: str) -> str:
        """Generate unique execution ID."""
        content_hash = hashlib.md5(prompt_content.encode()).hexdigest()[:8]
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"exec_{template_id}_{timestamp}_{content_hash}"
    
    def _generate_evolution_id(self, original_id: str, evolved_id: str) -> str:
        """Generate unique evolution ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"evo_{original_id}_to_{evolved_id}_{timestamp}"
    
    def _calculate_overall_metrics(self, executions: List[PromptExecution]) -> Dict[str, float]:
        """Calculate overall performance metrics."""
        total = len(executions)
        successful = sum(1 for e in executions if e.success)
        
        execution_times = [e.execution_time for e in executions if e.execution_time]
        feedback_scores = [e.feedback_score for e in executions if e.feedback_score]
        
        return {
            "total_executions": total,
            "success_rate": successful / total if total > 0 else 0,
            "avg_execution_time": statistics.mean(execution_times) if execution_times else 0,
            "avg_feedback_score": statistics.mean(feedback_scores) if feedback_scores else 0
        }
    
    def _analyze_template_performance(self, executions: List[PromptExecution]) -> Dict[str, Dict]:
        """Analyze performance by template."""
        template_groups = defaultdict(list)
        for execution in executions:
            template_groups[execution.template_id].append(execution)
        
        template_performance = {}
        for template_id, template_executions in template_groups.items():
            total = len(template_executions)
            successful = sum(1 for e in template_executions if e.success)
            execution_times = [e.execution_time for e in template_executions if e.execution_time]
            
            template_performance[template_id] = {
                "executions": total,
                "success_rate": successful / total,
                "avg_execution_time": statistics.mean(execution_times) if execution_times else 0
            }
        
        return template_performance
    
    def _analyze_task_type_patterns(self, executions: List[PromptExecution]) -> Dict[str, Dict]:
        """Analyze performance patterns by task type."""
        task_groups = defaultdict(list)
        for execution in executions:
            task_groups[execution.task_type].append(execution)
        
        task_patterns = {}
        for task_type, task_executions in task_groups.items():
            total = len(task_executions)
            successful = sum(1 for e in task_executions if e.success)
            
            task_patterns[task_type] = {
                "executions": total,
                "success_rate": successful / total,
                "common_errors": self._extract_error_patterns(task_executions)
            }
        
        return task_patterns
    
    def _analyze_temporal_patterns(self, executions: List[PromptExecution]) -> Dict[str, Any]:
        """Analyze temporal performance patterns."""
        # Group by hour
        hourly_performance = defaultdict(list)
        for execution in executions:
            hour = execution.created_at.hour
            hourly_performance[hour].append(execution.success)
        
        hourly_stats = {}
        for hour, successes in hourly_performance.items():
            hourly_stats[hour] = {
                "executions": len(successes),
                "success_rate": sum(successes) / len(successes)
            }
        
        return {"hourly_patterns": hourly_stats}
    
    def _analyze_error_patterns(self, executions: List[PromptExecution]) -> Dict[str, int]:
        """Analyze common error patterns."""
        error_counts = defaultdict(int)
        
        for execution in executions:
            if not execution.success and execution.error_details:
                # Simple error categorization
                error_type = self._categorize_error(execution.error_details)
                error_counts[error_type] += 1
        
        return dict(error_counts)
    
    def _extract_error_patterns(self, executions: List[PromptExecution]) -> List[str]:
        """Extract common error patterns from executions."""
        error_patterns = []
        failed_executions = [e for e in executions if not e.success and e.error_details]
        
        for execution in failed_executions:
            error_type = self._categorize_error(execution.error_details)
            if error_type not in error_patterns:
                error_patterns.append(error_type)
        
        return error_patterns[:5]  # Return top 5 error patterns
    
    def _categorize_error(self, error_details: str) -> str:
        """Categorize error based on error details."""
        error_lower = error_details.lower()
        
        if "timeout" in error_lower:
            return "timeout_error"
        elif "rate limit" in error_lower:
            return "rate_limit_error"  
        elif "invalid" in error_lower:
            return "validation_error"
        elif "connection" in error_lower:
            return "connection_error"
        else:
            return "unknown_error"
    
    def _calculate_improvement_potential(self, executions: List[PromptExecution]) -> float:
        """Calculate the improvement potential for a template."""
        if not executions:
            return 0.0
        
        recent_executions = sorted(executions, key=lambda x: x.created_at, reverse=True)[:20]
        
        # Calculate various improvement indicators
        success_values = [1 if e.success else 0 for e in recent_executions]
        feedback_values = [e.feedback_score for e in recent_executions if e.feedback_score]
        
        success_variance = statistics.variance(success_values) if len(success_values) > 1 else 0
        feedback_variance = statistics.variance(feedback_values) if len(feedback_values) > 1 else 0
        
        # Higher variance indicates more room for improvement
        potential = min(success_variance + (feedback_variance / 10), 1.0)
        return potential
    
    def _extract_learning_signals(self, feedback_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract actionable learning signals from feedback data."""
        signals = {
            "feedback_score": feedback_data.get("score", 0.0),
            "improvement_areas": feedback_data.get("improvement_areas", []),
            "positive_aspects": feedback_data.get("positive_aspects", []),
            "improvement_potential": 0.0
        }
        
        # Calculate improvement potential based on feedback
        score = feedback_data.get("score", 0.0)
        if score < 3.0:
            signals["improvement_potential"] = 0.8
        elif score < 4.0:
            signals["improvement_potential"] = 0.4
        else:
            signals["improvement_potential"] = 0.1
        
        return signals
    
    async def _update_template_learning(self, template_id: str, learning_signals: Dict[str, Any]):
        """Update template with new learning insights."""
        template = self.db_session.query(PromptTemplate).filter_by(
            template_id=template_id
        ).first()
        
        if template:
            # Update performance score with learning rate
            new_score = learning_signals.get("feedback_score", 0.0)
            template.performance_score = (
                template.performance_score * (1 - self.learning_rate) + 
                new_score * self.learning_rate
            )
            template.usage_count += 1
    
    async def _get_evolution_candidates(self, batch_size: int) -> List[str]:
        """Get templates that are candidates for evolution."""
        # Query templates with sufficient usage and room for improvement
        templates = self.db_session.query(PromptTemplate).filter(
            PromptTemplate.is_active == True,
            PromptTemplate.usage_count >= self.min_samples_for_evolution
        ).order_by(PromptTemplate.performance_score.asc()).limit(batch_size).all()
        
        return [t.template_id for t in templates]
    
    async def _schedule_ab_testing(self, original_template_id: str, evolved_template_id: str):
        """Schedule A/B testing between original and evolved templates."""
        # This would integrate with your existing A/B testing system
        # For now, we'll just log the scheduling
        self.logger.info(f"Scheduled A/B testing: {original_template_id} vs {evolved_template_id}")
    
    def _generate_recommendations(self, patterns: Dict[str, Any]) -> List[str]:
        """Generate actionable recommendations based on performance patterns."""
        recommendations = []
        
        overall_metrics = patterns.get("overall_metrics", {})
        if overall_metrics.get("success_rate", 0) < 0.8:
            recommendations.append("Overall success rate is below 80%. Consider reviewing and refining underperforming templates.")
        
        template_performance = patterns.get("template_performance", {})
        low_performing_templates = [
            tid for tid, metrics in template_performance.items() 
            if metrics.get("success_rate", 0) < 0.7
        ]
        
        if low_performing_templates:
            recommendations.append(f"Templates requiring immediate attention: {', '.join(low_performing_templates[:3])}")
        
        error_patterns = patterns.get("error_patterns", {})
        if error_patterns:
            top_error = max(error_patterns.keys(), key=lambda k: error_patterns[k])
            recommendations.append(f"Most common error type '{top_error}' should be addressed systematically.")
        
        return recommendations