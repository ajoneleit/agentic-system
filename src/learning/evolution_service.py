"""
Background Evolution Service for continuous prompt improvement.

This module provides a background service that runs continuous prompt evolution
cycles, monitoring performance, and triggering improvements automatically.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from src.learning.prompt_evolution import PromptEvolutionSystem


logger = logging.getLogger(__name__)


class EvolutionBackgroundService:
    """
    Background service that runs continuous prompt evolution cycles.
    
    This service operates autonomously to:
    - Monitor prompt performance in real-time
    - Trigger evolution cycles based on performance thresholds
    - Analyze patterns and generate insights
    - Maintain system health and optimization
    """
    
    def __init__(self, prompt_evolution_system: PromptEvolutionSystem, config: Dict[str, Any]):
        """Initialize the background evolution service.
        
        Args:
            prompt_evolution_system: The evolution system to manage
            config: Service configuration parameters
        """
        self.evolution_system = prompt_evolution_system
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.running = False
        
        # Configuration parameters
        self.evolution_interval = config.get("evolution_interval_hours", 6)
        self.analysis_interval = config.get("analysis_interval_hours", 1)
        self.monitoring_interval = config.get("monitoring_interval_minutes", 15)
        self.max_concurrent_evolutions = config.get("max_concurrent_evolutions", 3)
        
        # Service state
        self.last_evolution_time = None
        self.last_analysis_time = None
        self.active_evolutions = set()
        self.service_stats = {
            "total_cycles": 0,
            "total_evolutions": 0,
            "total_analyses": 0,
            "uptime_start": None,
            "last_error": None
        }
    
    async def start(self):
        """Start the background evolution service."""
        if self.running:
            self.logger.warning("Evolution service is already running")
            return
        
        self.running = True
        self.service_stats["uptime_start"] = datetime.utcnow()
        self.logger.info("Starting Prompt Evolution Background Service")
        
        try:
            # Start background tasks concurrently
            tasks = [
                asyncio.create_task(self._evolution_loop()),
                asyncio.create_task(self._analysis_loop()),
                asyncio.create_task(self._monitoring_loop()),
                asyncio.create_task(self._health_check_loop())
            ]
            
            # Wait for all tasks to complete
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except Exception as e:
            self.logger.error(f"Error in background service: {str(e)}")
            self.service_stats["last_error"] = str(e)
        finally:
            self.running = False
    
    async def stop(self):
        """Stop the background evolution service."""
        self.running = False
        
        # Wait for active evolutions to complete
        if self.active_evolutions:
            self.logger.info(f"Waiting for {len(self.active_evolutions)} active evolutions to complete")
            while self.active_evolutions and len(self.active_evolutions) > 0:
                await asyncio.sleep(1)
        
        self.logger.info("Prompt Evolution Background Service stopped")
    
    async def get_service_status(self) -> Dict[str, Any]:
        """Get current service status and statistics.
        
        Returns:
            Service status dictionary
        """
        uptime = None
        if self.service_stats["uptime_start"]:
            uptime = (datetime.utcnow() - self.service_stats["uptime_start"]).total_seconds()
        
        return {
            "running": self.running,
            "uptime_seconds": uptime,
            "active_evolutions": len(self.active_evolutions),
            "last_evolution_time": self.last_evolution_time,
            "last_analysis_time": self.last_analysis_time,
            "stats": self.service_stats,
            "config": {
                "evolution_interval_hours": self.evolution_interval,
                "analysis_interval_hours": self.analysis_interval,
                "monitoring_interval_minutes": self.monitoring_interval
            }
        }
    
    async def trigger_immediate_evolution(self, template_ids: list = None) -> Dict[str, Any]:
        """Trigger an immediate evolution cycle.
        
        Args:
            template_ids: Optional list of specific template IDs to evolve
            
        Returns:
            Evolution results
        """
        if not self.running:
            return {"error": "Service is not running"}
        
        try:
            if template_ids:
                # Evolve specific templates
                results = []
                for template_id in template_ids:
                    if len(self.active_evolutions) < self.max_concurrent_evolutions:
                        evolution_id = f"manual_{template_id}_{int(asyncio.get_event_loop().time())}"
                        self.active_evolutions.add(evolution_id)
                        
                        try:
                            new_template_id = await self.evolution_system.autonomous_prompt_refinement(template_id)
                            if new_template_id:
                                results.append(new_template_id)
                        finally:
                            self.active_evolutions.discard(evolution_id)
                
                return {"evolved_templates": results, "requested_templates": template_ids}
            else:
                # Run standard evolution cycle
                return await self._run_evolution_cycle()
                
        except Exception as e:
            self.logger.error(f"Error in immediate evolution: {str(e)}")
            return {"error": str(e)}
    
    # Private service loop methods
    
    async def _evolution_loop(self):
        """Main evolution loop that runs periodically."""
        while self.running:
            try:
                self.logger.info("Starting scheduled evolution cycle")
                
                await self._run_evolution_cycle()
                self.last_evolution_time = datetime.utcnow()
                self.service_stats["total_cycles"] += 1
                
                # Wait for next cycle
                await asyncio.sleep(self.evolution_interval * 3600)  # Convert hours to seconds
                
            except Exception as e:
                self.logger.error(f"Error in evolution loop: {str(e)}")
                self.service_stats["last_error"] = str(e)
                await asyncio.sleep(300)  # Wait 5 minutes before retrying
    
    async def _analysis_loop(self):
        """Analysis loop that runs more frequently to monitor performance."""
        while self.running:
            try:
                # Analyze recent performance
                patterns = await self.evolution_system.analyze_performance_patterns(
                    time_window_hours=self.analysis_interval
                )
                
                # Log important insights
                if patterns.get("recommendations"):
                    self.logger.info(f"Performance insights: {patterns['recommendations']}")
                
                # Check for urgent evolution needs
                await self._check_urgent_evolution_needs(patterns)
                
                self.last_analysis_time = datetime.utcnow()
                self.service_stats["total_analyses"] += 1
                
                # Wait for next analysis
                await asyncio.sleep(self.analysis_interval * 3600)
                
            except Exception as e:
                self.logger.error(f"Error in analysis loop: {str(e)}")
                self.service_stats["last_error"] = str(e)
                await asyncio.sleep(300)  # Wait 5 minutes before retrying
    
    async def _monitoring_loop(self):
        """Monitoring loop for real-time system health."""
        while self.running:
            try:
                # Monitor system health
                await self._monitor_system_health()
                
                # Clean up completed evolutions
                self._cleanup_completed_evolutions()
                
                # Wait for next monitoring cycle
                await asyncio.sleep(self.monitoring_interval * 60)  # Convert minutes to seconds
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {str(e)}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    async def _health_check_loop(self):
        """Health check loop to ensure system components are functioning."""
        while self.running:
            try:
                # Check database connectivity
                await self._check_database_health()
                
                # Check OpenAI client health
                await self._check_openai_health()
                
                # Check template integrity
                await self._check_template_integrity()
                
                # Wait for next health check (every 30 minutes)
                await asyncio.sleep(1800)
                
            except Exception as e:
                self.logger.error(f"Error in health check loop: {str(e)}")
                await asyncio.sleep(300)  # Wait 5 minutes before retrying
    
    # Helper methods
    
    async def _run_evolution_cycle(self) -> Dict[str, Any]:
        """Run a complete evolution cycle."""
        if len(self.active_evolutions) >= self.max_concurrent_evolutions:
            self.logger.warning("Max concurrent evolutions reached, skipping cycle")
            return {"skipped": True, "reason": "max_concurrent_limit"}
        
        try:
            # Run template evolution
            evolved_templates = await self.evolution_system.evolve_templates(
                batch_size=self.config.get("evolution_batch_size", 5)
            )
            
            self.service_stats["total_evolutions"] += len(evolved_templates)
            
            if evolved_templates:
                self.logger.info(f"Evolution cycle completed. Evolved {len(evolved_templates)} templates")
                return {"evolved_templates": evolved_templates, "count": len(evolved_templates)}
            else:
                self.logger.info("Evolution cycle completed. No templates evolved")
                return {"evolved_templates": [], "count": 0}
                
        except Exception as e:
            self.logger.error(f"Error in evolution cycle: {str(e)}")
            return {"error": str(e)}
    
    async def _check_urgent_evolution_needs(self, patterns: Dict[str, Any]):
        """Check if any templates need urgent evolution based on recent performance."""
        template_performance = patterns.get("template_performance", {})
        
        urgent_templates = []
        for template_id, metrics in template_performance.items():
            if (metrics.get("success_rate", 1.0) < 0.5 and 
                metrics.get("executions", 0) >= 5):
                urgent_templates.append(template_id)
        
        # Trigger immediate evolution for urgent cases
        for template_id in urgent_templates:
            if len(self.active_evolutions) < self.max_concurrent_evolutions:
                self.logger.warning(f"Triggering urgent evolution for template {template_id}")
                
                evolution_id = f"urgent_{template_id}_{int(asyncio.get_event_loop().time())}"
                self.active_evolutions.add(evolution_id)
                
                # Run evolution in background
                asyncio.create_task(self._run_urgent_evolution(template_id, evolution_id))
    
    async def _run_urgent_evolution(self, template_id: str, evolution_id: str):
        """Run urgent evolution for a specific template."""
        try:
            await self.evolution_system.autonomous_prompt_refinement(template_id)
            self.logger.info(f"Completed urgent evolution for template {template_id}")
        except Exception as e:
            self.logger.error(f"Error in urgent evolution for {template_id}: {str(e)}")
        finally:
            self.active_evolutions.discard(evolution_id)
    
    async def _monitor_system_health(self):
        """Monitor overall system health."""
        try:
            # Check recent execution patterns
            recent_patterns = await self.evolution_system.analyze_performance_patterns(1)  # Last hour
            
            overall_metrics = recent_patterns.get("overall_metrics", {})
            success_rate = overall_metrics.get("success_rate", 1.0)
            
            # Alert if success rate drops significantly
            if success_rate < 0.6:
                self.logger.warning(f"System success rate dropped to {success_rate:.2f}")
            
            # Check for system overload
            if len(self.active_evolutions) >= self.max_concurrent_evolutions:
                self.logger.warning("System approaching max concurrent evolution limit")
                
        except Exception as e:
            self.logger.error(f"Error monitoring system health: {str(e)}")
    
    def _cleanup_completed_evolutions(self):
        """Clean up completed evolution tracking."""
        # In a real implementation, you'd check if evolutions are actually complete
        # For now, we'll just ensure the set doesn't grow indefinitely
        if len(self.active_evolutions) > self.max_concurrent_evolutions * 2:
            self.logger.warning("Cleaning up stale evolution tracking")
            # Remove oldest half of tracked evolutions
            to_remove = list(self.active_evolutions)[:len(self.active_evolutions) // 2]
            for evolution_id in to_remove:
                self.active_evolutions.discard(evolution_id)
    
    async def _check_database_health(self):
        """Check database connectivity and health."""
        try:
            # Simple query to test database connectivity
            count = self.evolution_system.db_session.query(
                self.evolution_system.PromptTemplate
            ).count()
            self.logger.debug(f"Database health check passed. {count} templates in database.")
        except Exception as e:
            self.logger.error(f"Database health check failed: {str(e)}")
            raise
    
    async def _check_openai_health(self):
        """Check OpenAI client connectivity."""
        try:
            # Test with a simple message
            test_messages = [{"role": "user", "content": "test"}]
            await self.evolution_system.openai_client.create_message(
                messages=test_messages,
                max_tokens=10
            )
            self.logger.debug("OpenAI client health check passed")
        except Exception as e:
            self.logger.error(f"OpenAI client health check failed: {str(e)}")
            # Don't raise here as this might be temporary
    
    async def _check_template_integrity(self):
        """Check template data integrity."""
        try:
            # Check for templates without content
            empty_templates = self.evolution_system.db_session.query(
                self.evolution_system.PromptTemplate
            ).filter(
                self.evolution_system.PromptTemplate.template_content.is_(None)
            ).count()
            
            if empty_templates > 0:
                self.logger.warning(f"Found {empty_templates} templates with empty content")
            
            # Check for templates with very low performance that should be deactivated
            low_performance_templates = self.evolution_system.db_session.query(
                self.evolution_system.PromptTemplate
            ).filter(
                self.evolution_system.PromptTemplate.is_active == True,
                self.evolution_system.PromptTemplate.performance_score < 0.3,
                self.evolution_system.PromptTemplate.usage_count > 10
            ).count()
            
            if low_performance_templates > 0:
                self.logger.info(f"Found {low_performance_templates} low-performance templates that may need review")
                
        except Exception as e:
            self.logger.error(f"Template integrity check failed: {str(e)}")


class EvolutionScheduler:
    """
    Scheduler for coordinating evolution activities across the system.
    
    This class provides more granular control over when and how evolution
    activities are scheduled and executed.
    """
    
    def __init__(self, evolution_service: EvolutionBackgroundService):
        """Initialize the evolution scheduler.
        
        Args:
            evolution_service: Background service to schedule activities for
        """
        self.evolution_service = evolution_service
        self.logger = logging.getLogger(__name__)
        self.scheduled_tasks = {}
    
    async def schedule_evolution(self, template_id: str, delay_hours: float) -> str:
        """Schedule evolution for a specific template.
        
        Args:
            template_id: Template to evolve
            delay_hours: Hours to wait before evolution
            
        Returns:
            Scheduled task ID
        """
        task_id = f"scheduled_{template_id}_{int(asyncio.get_event_loop().time())}"
        
        async def scheduled_evolution():
            await asyncio.sleep(delay_hours * 3600)
            try:
                await self.evolution_service.trigger_immediate_evolution([template_id])
                self.logger.info(f"Completed scheduled evolution for template {template_id}")
            except Exception as e:
                self.logger.error(f"Error in scheduled evolution: {str(e)}")
            finally:
                self.scheduled_tasks.pop(task_id, None)
        
        # Create and store the task
        task = asyncio.create_task(scheduled_evolution())
        self.scheduled_tasks[task_id] = task
        
        self.logger.info(f"Scheduled evolution for template {template_id} in {delay_hours} hours")
        return task_id
    
    async def cancel_scheduled_evolution(self, task_id: str) -> bool:
        """Cancel a scheduled evolution.
        
        Args:
            task_id: ID of scheduled task to cancel
            
        Returns:
            True if task was cancelled successfully
        """
        if task_id in self.scheduled_tasks:
            task = self.scheduled_tasks[task_id]
            task.cancel()
            del self.scheduled_tasks[task_id]
            self.logger.info(f"Cancelled scheduled evolution task {task_id}")
            return True
        return False
    
    def get_scheduled_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get information about currently scheduled tasks.
        
        Returns:
            Dictionary of scheduled task information
        """
        return {
            task_id: {
                "done": task.done(),
                "cancelled": task.cancelled(),
                "created_at": asyncio.get_event_loop().time()  # Approximation
            }
            for task_id, task in self.scheduled_tasks.items()
        }