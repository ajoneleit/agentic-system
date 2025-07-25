"""
Demonstration of the Prompt Evolution System.

This script shows how to set up and use the Prompt Evolution System
for autonomous prompt improvement and learning integration.
"""

import asyncio
import logging
import os
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.clients.openai_client import OpenAIClient, OpenAIModel
from src.learning import (
    PromptEvolutionSystem,
    AgentPromptIntegration,
    EvolutionBackgroundService,
    EvolutionMetricsCollector
)
from src.learning.prompt_evolution import Base, PromptTemplate


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def setup_database():
    """Set up the database for demonstration."""
    # Use SQLite for the demo (in production, use PostgreSQL or similar)
    engine = create_engine("sqlite:///prompt_evolution_demo.db")
    Base.metadata.create_all(engine)
    
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


async def create_sample_templates(session):
    """Create sample prompt templates for demonstration."""
    templates = [
        {
            "template_id": "code_generation_v1",
            "template_content": """You are a professional software developer. Please implement the following requirement:

Requirement: {task_description}

Please provide clean, well-documented code with appropriate error handling.
""",
            "variables": ["task_description"],
            "category": "code_generation"
        },
        {
            "template_id": "test_generation_v1", 
            "template_content": """You are a test engineer. Create comprehensive tests for the following code:

Code to test: {code_content}

Requirements:
- Include unit tests
- Test edge cases
- Use appropriate testing framework
- Add clear test descriptions

Test type: {test_type}
""",
            "variables": ["code_content", "test_type"],
            "category": "test_generation"
        },
        {
            "template_id": "documentation_v1",
            "template_content": """You are a technical writer. Create clear documentation for:

Component: {component_name}
Purpose: {component_purpose}

Please include:
- Clear description
- Usage examples
- API reference if applicable
- Best practices
""",
            "variables": ["component_name", "component_purpose"],
            "category": "documentation"
        }
    ]
    
    for template_data in templates:
        template = PromptTemplate(
            template_id=template_data["template_id"],
            template_content=template_data["template_content"],
            variables=template_data["variables"],
            category=template_data["category"],
            is_active=True
        )
        session.add(template)
    
    session.commit()
    logger.info(f"Created {len(templates)} sample templates")


async def simulate_prompt_usage(evolution_system: PromptEvolutionSystem):
    """Simulate prompt usage with varying success rates."""
    logger.info("Simulating prompt usage...")
    
    # Simulate different execution scenarios
    scenarios = [
        # Code generation scenarios
        {
            "template_id": "code_generation_v1",
            "task_type": "code_generation",
            "scenarios": [
                {"success": True, "time": 3.2, "feedback": 4.5},
                {"success": True, "time": 2.8, "feedback": 4.0},
                {"success": False, "time": 8.1, "error": "timeout", "feedback": 2.0},
                {"success": True, "time": 4.1, "feedback": 3.8},
                {"success": False, "time": 5.5, "error": "compilation error", "feedback": 2.5},
                {"success": True, "time": 3.5, "feedback": 4.2},
                {"success": True, "time": 2.9, "feedback": 4.1},
                {"success": False, "time": 7.2, "error": "invalid syntax", "feedback": 1.8},
            ]
        },
        # Test generation scenarios  
        {
            "template_id": "test_generation_v1",
            "task_type": "test_generation",
            "scenarios": [
                {"success": True, "time": 2.5, "feedback": 4.8},
                {"success": True, "time": 3.1, "feedback": 4.6},
                {"success": True, "time": 2.9, "feedback": 4.5},
                {"success": False, "time": 6.8, "error": "framework error", "feedback": 3.0},
                {"success": True, "time": 3.3, "feedback": 4.7},
                {"success": True, "time": 2.7, "feedback": 4.4},
            ]
        },
        # Documentation scenarios
        {
            "template_id": "documentation_v1", 
            "task_type": "documentation",
            "scenarios": [
                {"success": True, "time": 4.2, "feedback": 3.5},
                {"success": False, "time": 9.1, "error": "incomplete", "feedback": 2.2},
                {"success": True, "time": 5.1, "feedback": 3.8},
                {"success": False, "time": 8.5, "error": "unclear", "feedback": 2.8},
                {"success": True, "time": 4.8, "feedback": 3.6},
                {"success": False, "time": 7.9, "error": "missing examples", "feedback": 2.5},
                {"success": True, "time": 4.5, "feedback": 3.9},
            ]
        }
    ]
    
    # Record executions
    execution_ids = []
    for template_scenario in scenarios:
        template_id = template_scenario["template_id"]
        task_type = template_scenario["task_type"]
        
        for i, scenario in enumerate(template_scenario["scenarios"]):
            # Record execution
            execution_id = await evolution_system.record_execution(
                template_id=template_id,
                prompt_content=f"Sample prompt content for {template_id} execution {i}",
                task_type=task_type,
                success=scenario["success"],
                execution_time=scenario["time"],
                performance_metrics={"scenario_id": i},
                error_details=scenario.get("error")
            )
            
            execution_ids.append(execution_id)
            
            # Provide feedback
            if "feedback" in scenario:
                await evolution_system.integrate_learning(execution_id, {
                    "score": scenario["feedback"],
                    "improvement_areas": ["clarity", "examples"] if scenario["feedback"] < 4.0 else [],
                    "positive_aspects": ["structure"] if scenario["feedback"] >= 4.0 else []
                })
    
    logger.info(f"Simulated {len(execution_ids)} prompt executions")
    return execution_ids


async def demonstrate_analysis(evolution_system: PromptEvolutionSystem):
    """Demonstrate performance analysis capabilities."""
    logger.info("\n=== Performance Analysis ===")
    
    # Analyze performance patterns
    patterns = await evolution_system.analyze_performance_patterns(24)
    
    print(f"\nOverall Metrics:")
    overall = patterns["overall_metrics"]
    print(f"  Total Executions: {overall['total_executions']}")
    print(f"  Success Rate: {overall['success_rate']:.2%}")
    print(f"  Avg Execution Time: {overall['avg_execution_time']:.2f}s")
    print(f"  Avg Feedback Score: {overall['avg_feedback_score']:.2f}")
    
    print(f"\nTemplate Performance:")
    for template_id, metrics in patterns["template_performance"].items():
        print(f"  {template_id}:")
        print(f"    Success Rate: {metrics['success_rate']:.2%}")
        print(f"    Executions: {metrics['executions']}")
        print(f"    Avg Time: {metrics['avg_execution_time']:.2f}s")
    
    print(f"\nTask Type Patterns:")
    for task_type, metrics in patterns["task_type_patterns"].items():
        print(f"  {task_type}:")
        print(f"    Success Rate: {metrics['success_rate']:.2%}")
        print(f"    Executions: {metrics['executions']}")
        print(f"    Common Errors: {', '.join(metrics['common_errors'][:3])}")
    
    if patterns["recommendations"]:
        print(f"\nRecommendations:")
        for rec in patterns["recommendations"]:
            print(f"  • {rec}")


async def demonstrate_evolution(evolution_system: PromptEvolutionSystem):
    """Demonstrate prompt evolution capabilities."""
    logger.info("\n=== Prompt Evolution ===")
    
    # Get metrics for templates before evolution
    print("\nTemplate Metrics Before Evolution:")
    for template_id in ["code_generation_v1", "test_generation_v1", "documentation_v1"]:
        metrics = await evolution_system.get_template_metrics(template_id)
        print(f"  {template_id}:")
        print(f"    Success Rate: {metrics.success_rate:.2%}")
        print(f"    Improvement Potential: {metrics.improvement_potential:.2f}")
        print(f"    Usage Frequency: {metrics.usage_frequency}")
    
    # Trigger evolution for underperforming templates
    print("\nTriggering Evolution...")
    evolved_templates = await evolution_system.evolve_templates(batch_size=3)
    
    if evolved_templates:
        print(f"Evolved Templates: {', '.join(evolved_templates)}")
        
        # Show evolved template content
        for template_id in evolved_templates[:2]:  # Show first 2 for brevity
            template = evolution_system.db_session.query(PromptTemplate).filter_by(
                template_id=template_id
            ).first()
            
            if template:
                print(f"\n--- Evolved Template: {template_id} ---")
                print(f"Parent: {template.parent_template_id}")
                print(f"Version: {template.version}")
                print(f"Content: {template.template_content[:200]}...")
    else:
        print("No templates evolved (may already be performing well)")


async def demonstrate_integration(evolution_system: PromptEvolutionSystem):
    """Demonstrate agent integration capabilities."""
    logger.info("\n=== Agent Integration Demo ===")
    
    # Mock agent manager for demonstration
    class MockAgentManager:
        async def execute_task(self, agent_id, prompt_content, task_type):
            # Simulate task execution
            import random
            success = random.random() > 0.2  # 80% success rate
            return {
                "success": success,
                "result": f"Mock result for {task_type}",
                "metrics": {"execution_time": random.uniform(1.0, 5.0)},
                "error": "Mock error" if not success else None
            }
    
    # Create integration
    integration = AgentPromptIntegration(evolution_system, MockAgentManager())
    
    # Execute tasks with evolution tracking
    print("\nExecuting tasks with evolution tracking:")
    for i in range(3):
        result = await integration.execute_with_evolution(
            agent_id=f"demo_agent_{i}",
            task_type="code_generation",
            template_id="code_generation_v1",
            variables={"task_description": f"Demo task {i}"}
        )
        
        print(f"  Task {i}: Success = {result['success']}")
        if "evolution_tracking" in result:
            tracking = result["evolution_tracking"]
            print(f"    Execution ID: {tracking['execution_id']}")
            print(f"    Template: {tracking['template_id']} v{tracking['template_version']}")


async def demonstrate_background_service(evolution_system: PromptEvolutionSystem):
    """Demonstrate background evolution service."""
    logger.info("\n=== Background Service Demo ===")
    
    # Configure service for quick demo
    service_config = {
        "evolution_interval_hours": 0.001,  # Very short for demo
        "analysis_interval_hours": 0.001,
        "monitoring_interval_minutes": 0.01,
        "max_concurrent_evolutions": 2,
        "evolution_batch_size": 2
    }
    
    service = EvolutionBackgroundService(evolution_system, service_config)
    
    # Get initial status
    status = await service.get_service_status()
    print(f"Service Status: Running = {status['running']}")
    print(f"Configuration: {status['config']}")
    
    # Trigger immediate evolution
    print("\nTriggering immediate evolution...")
    result = await service.trigger_immediate_evolution(["documentation_v1"])
    print(f"Evolution Result: {result}")


async def demonstrate_metrics_collection(evolution_system: PromptEvolutionSystem):
    """Demonstrate metrics collection capabilities."""
    logger.info("\n=== Metrics Collection ===")
    
    collector = EvolutionMetricsCollector(evolution_system)
    
    # Collect system metrics
    metrics = await collector.collect_system_metrics()
    print(f"\nSystem Metrics:")
    print(f"  Templates: {metrics['templates']['total']} total, {metrics['templates']['active']} active")
    print(f"  Executions: {metrics['executions']['total']} total")
    
    # Get top performing templates
    top_templates = await collector.get_top_performing_templates(limit=5)
    print(f"\nTop Performing Templates:")
    for i, template in enumerate(top_templates[:3], 1):
        print(f"  {i}. {template['template_id']} (score: {template['performance_score']:.2f})")
        print(f"     Usage: {template['usage_count']}, Success Rate: {template['metrics'].success_rate:.2%}")


async def main():
    """Main demonstration function."""
    print("🚀 Prompt Evolution System Demonstration")
    print("=" * 50)
    
    try:
        # Check for OpenAI API key
        if not os.getenv('OPENAI_API_KEY'):
            logger.warning("OPENAI_API_KEY not found. Using mock responses for evolution.")
            # In a real scenario, you'd need a valid API key
            # For demo purposes, we'll continue with mock data
        
        # Set up database
        session = await setup_database()
        
        # Create OpenAI client (with mock for demo if no API key)
        if os.getenv('OPENAI_API_KEY'):
            openai_client = OpenAIClient(model=OpenAIModel.O3_MINI)
        else:
            # Mock client for demo
            from unittest.mock import AsyncMock
            openai_client = AsyncMock()
            openai_client.create_message.return_value = {
                "content": "This is an improved version of the original prompt with enhanced clarity, better structure, and more specific instructions that should lead to higher success rates.",
                "model": "o3-mini",
                "usage": {"input_tokens": 200, "output_tokens": 100}
            }
        
        # Configure evolution system
        config = {
            "learning_rate": 0.1,
            "exploration_rate": 0.2,
            "min_samples_for_evolution": 5,
            "min_success_rate": 0.8,
            "improvement_threshold": 0.3,
            "min_feedback_score": 3.0,
            "max_execution_time": 10.0,
            "evolution_batch_size": 3
        }
        
        # Initialize evolution system
        evolution_system = PromptEvolutionSystem(session, openai_client, config)
        
        # Create sample templates
        await create_sample_templates(session)
        
        # Simulate usage
        await simulate_prompt_usage(evolution_system)
        
        # Demonstrate capabilities
        await demonstrate_analysis(evolution_system)
        await demonstrate_evolution(evolution_system)
        await demonstrate_integration(evolution_system)
        await demonstrate_background_service(evolution_system)
        await demonstrate_metrics_collection(evolution_system)
        
        print(f"\n✅ Demonstration completed successfully!")
        print(f"\nKey Features Demonstrated:")
        print(f"  • Autonomous prompt refinement using OpenAI o3")
        print(f"  • Performance analysis and pattern recognition")
        print(f"  • Template evolution based on empirical results")
        print(f"  • Learning integration from user feedback")
        print(f"  • Agent integration for seamless operation")
        print(f"  • Background service for continuous improvement")
        print(f"  • Comprehensive metrics and monitoring")
        
    except Exception as e:
        logger.error(f"Error in demonstration: {str(e)}")
        raise
    finally:
        if 'session' in locals():
            session.close()


if __name__ == "__main__":
    asyncio.run(main())