"""
Test cases for the Prompt Evolution System.

This module provides comprehensive tests for the prompt evolution system
including database operations, evolution logic, and integration points.
"""

import asyncio
import pytest
import tempfile
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.clients.openai_client import OpenAIClient
from src.learning.prompt_evolution import (
    Base,
    PromptEvolutionSystem,
    PromptTemplate,
    PromptExecution,
    EvolutionHistory,
    PromptMetrics
)
from src.learning.agent_integration import AgentPromptIntegration
from src.learning.evolution_service import EvolutionBackgroundService


@pytest.fixture
def db_session():
    """Create an in-memory database session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    yield session
    
    session.close()


@pytest.fixture
def mock_openai_client():
    """Create a mock OpenAI client for testing."""
    client = AsyncMock(spec=OpenAIClient)
    client.create_message.return_value = {
        "content": "Improved prompt content",
        "model": "o3-mini",
        "usage": {"input_tokens": 100, "output_tokens": 50}
    }
    return client


@pytest.fixture
def evolution_system(db_session, mock_openai_client):
    """Create a PromptEvolutionSystem instance for testing."""
    config = {
        "learning_rate": 0.1,
        "exploration_rate": 0.2,
        "min_samples_for_evolution": 5,
        "min_success_rate": 0.8,
        "improvement_threshold": 0.3,
        "min_feedback_score": 3.0,
        "max_execution_time": 10.0
    }
    
    return PromptEvolutionSystem(db_session, mock_openai_client, config)


class TestPromptEvolutionSystem:
    """Test cases for the core PromptEvolutionSystem class."""
    
    def test_initialization(self, evolution_system):
        """Test system initialization."""
        assert evolution_system is not None
        assert len(evolution_system.evolution_strategies) == 4
        assert evolution_system.learning_rate == 0.1
        assert evolution_system.exploration_rate == 0.2
    
    @pytest.mark.asyncio
    async def test_record_execution(self, evolution_system):
        """Test recording prompt execution."""
        # Create a test template first
        template = PromptTemplate(
            template_id="test_template",
            template_content="Test prompt: {task_description}",
            variables=["task_description"],
            category="test",
            is_active=True
        )
        evolution_system.db_session.add(template)
        evolution_system.db_session.commit()
        
        # Record an execution
        execution_id = await evolution_system.record_execution(
            template_id="test_template",
            prompt_content="Test prompt: implement a function",
            task_type="code_generation",
            success=True,
            execution_time=2.5,
            performance_metrics={"lines_of_code": 20}
        )
        
        assert execution_id is not None
        assert "exec_test_template" in execution_id
        
        # Verify execution was stored
        execution = evolution_system.db_session.query(PromptExecution).filter_by(
            execution_id=execution_id
        ).first()
        
        assert execution is not None
        assert execution.template_id == "test_template"
        assert execution.success is True
        assert execution.execution_time == 2.5
    
    @pytest.mark.asyncio
    async def test_get_template_metrics(self, evolution_system):
        """Test getting template performance metrics."""
        # Create test template and executions
        template = PromptTemplate(
            template_id="metrics_test",
            template_content="Metrics test prompt",
            category="test",
            is_active=True
        )
        evolution_system.db_session.add(template)
        
        # Add some test executions
        for i in range(10):
            execution = PromptExecution(
                execution_id=f"test_exec_{i}",
                template_id="metrics_test",
                prompt_content="test content",
                task_type="test",
                success=i < 8,  # 80% success rate
                execution_time=1.0 + (i * 0.1),
                feedback_score=3.5 + (i * 0.1) if i < 5 else None
            )
            evolution_system.db_session.add(execution)
        
        evolution_system.db_session.commit()
        
        # Get metrics
        metrics = await evolution_system.get_template_metrics("metrics_test")
        
        assert isinstance(metrics, PromptMetrics)
        assert metrics.success_rate == 0.8
        assert metrics.usage_frequency == 10
        assert metrics.avg_execution_time > 1.0
    
    @pytest.mark.asyncio
    async def test_autonomous_prompt_refinement(self, evolution_system):
        """Test autonomous prompt refinement."""
        # Create a template with poor performance
        template = PromptTemplate(
            template_id="poor_template",
            template_content="Poor prompt",
            category="test",
            version=1,
            is_active=True,
            performance_score=0.3
        )
        evolution_system.db_session.add(template)
        
        # Add poor performance executions
        for i in range(10):
            execution = PromptExecution(
                execution_id=f"poor_exec_{i}",
                template_id="poor_template",
                prompt_content="poor content",
                task_type="test",
                success=i < 3,  # 30% success rate
                execution_time=5.0,
                feedback_score=2.0
            )
            evolution_system.db_session.add(execution)
        
        evolution_system.db_session.commit()
        
        # Test refinement
        new_template_id = await evolution_system.autonomous_prompt_refinement("poor_template")
        
        assert new_template_id is not None
        assert "poor_template_v2" in new_template_id
        
        # Verify new template was created
        new_template = evolution_system.db_session.query(PromptTemplate).filter_by(
            template_id=new_template_id
        ).first()
        
        assert new_template is not None
        assert new_template.version == 2
        assert new_template.parent_template_id == "poor_template"
    
    @pytest.mark.asyncio
    async def test_analyze_performance_patterns(self, evolution_system):
        """Test performance pattern analysis."""
        # Create test data
        template = PromptTemplate(
            template_id="pattern_test",
            template_content="Pattern test prompt",
            category="test",
            is_active=True
        )
        evolution_system.db_session.add(template)
        
        # Add executions with different patterns
        now = datetime.utcnow()
        for i in range(20):
            execution = PromptExecution(
                execution_id=f"pattern_exec_{i}",
                template_id="pattern_test",
                prompt_content="pattern content",
                task_type="test_task",
                success=i % 2 == 0,  # Alternating success/failure
                execution_time=1.0 + i * 0.1,
                created_at=now - timedelta(hours=i),
                error_details="timeout error" if i % 2 == 1 else None
            )
            evolution_system.db_session.add(execution)
        
        evolution_system.db_session.commit()
        
        # Analyze patterns
        patterns = await evolution_system.analyze_performance_patterns(24)
        
        assert "overall_metrics" in patterns
        assert "template_performance" in patterns
        assert "task_type_patterns" in patterns
        assert "error_patterns" in patterns
        assert "recommendations" in patterns
        
        # Check overall metrics
        overall = patterns["overall_metrics"]
        assert overall["total_executions"] == 20
        assert overall["success_rate"] == 0.5
    
    @pytest.mark.asyncio
    async def test_integrate_learning(self, evolution_system):
        """Test learning integration from feedback."""
        # Create test execution
        execution = PromptExecution(
            execution_id="learning_test",
            template_id="learning_template",
            prompt_content="learning content",
            task_type="test",
            success=True,
            execution_time=1.0
        )
        evolution_system.db_session.add(execution)
        evolution_system.db_session.commit()
        
        # Provide feedback
        feedback_data = {
            "score": 4.5,
            "improvement_areas": ["clarity", "examples"],
            "positive_aspects": ["structure", "completeness"]
        }
        
        result = await evolution_system.integrate_learning("learning_test", feedback_data)
        
        assert result is True
        
        # Verify feedback was integrated
        updated_execution = evolution_system.db_session.query(PromptExecution).filter_by(
            execution_id="learning_test"
        ).first()
        
        assert updated_execution.feedback_score == 4.5
        assert "improvement_areas" in updated_execution.performance_metrics


class TestAgentPromptIntegration:
    """Test cases for agent integration functionality."""
    
    @pytest.fixture
    def mock_agent_manager(self):
        """Create a mock agent manager for testing."""
        manager = AsyncMock()
        manager.execute_task.return_value = {
            "success": True,
            "metrics": {"execution_time": 2.0},
            "result": "Task completed successfully"
        }
        return manager
    
    @pytest.fixture
    def integration(self, evolution_system, mock_agent_manager):
        """Create an AgentPromptIntegration instance."""
        return AgentPromptIntegration(evolution_system, mock_agent_manager)
    
    @pytest.mark.asyncio
    async def test_execute_with_evolution(self, integration, evolution_system):
        """Test executing tasks with evolution tracking."""
        # Create test template
        template = PromptTemplate(
            template_id="integration_test",
            template_content="Integration test: {task_name}",
            variables=["task_name"],
            category="test",
            is_active=True
        )
        evolution_system.db_session.add(template)
        evolution_system.db_session.commit()
        
        # Execute with evolution tracking
        result = await integration.execute_with_evolution(
            agent_id="test_agent",
            task_type="test_task",
            template_id="integration_test",
            variables={"task_name": "test task"}
        )
        
        assert result["success"] is True
        assert "evolution_tracking" in result
        assert "execution_id" in result["evolution_tracking"]
        assert "template_id" in result["evolution_tracking"]
    
    @pytest.mark.asyncio
    async def test_provide_feedback(self, integration, evolution_system):
        """Test providing feedback through integration layer."""
        # Create test execution
        execution = PromptExecution(
            execution_id="feedback_test",
            template_id="feedback_template",
            prompt_content="feedback content",
            task_type="test",
            success=True,
            execution_time=1.0
        )
        evolution_system.db_session.add(execution)
        evolution_system.db_session.commit()
        
        # Provide feedback
        feedback_data = {"score": 4.0, "improvement_areas": ["clarity"]}
        result = await integration.provide_feedback("feedback_test", feedback_data)
        
        assert result is True


class TestEvolutionBackgroundService:
    """Test cases for the background evolution service."""
    
    @pytest.fixture
    def service_config(self):
        """Configuration for background service testing."""
        return {
            "evolution_interval_hours": 0.001,  # Very short for testing
            "analysis_interval_hours": 0.001,
            "monitoring_interval_minutes": 0.01,
            "max_concurrent_evolutions": 2,
            "evolution_batch_size": 3
        }
    
    @pytest.fixture
    def background_service(self, evolution_system, service_config):
        """Create a background service for testing."""
        return EvolutionBackgroundService(evolution_system, service_config)
    
    def test_initialization(self, background_service):
        """Test background service initialization."""
        assert background_service is not None
        assert not background_service.running
        assert background_service.evolution_interval == 0.001
    
    @pytest.mark.asyncio
    async def test_service_status(self, background_service):
        """Test getting service status."""
        status = await background_service.get_service_status()
        
        assert "running" in status
        assert "uptime_seconds" in status
        assert "active_evolutions" in status
        assert "stats" in status
        assert "config" in status
    
    @pytest.mark.asyncio
    async def test_trigger_immediate_evolution(self, background_service, evolution_system):
        """Test triggering immediate evolution."""
        # Create test template
        template = PromptTemplate(
            template_id="immediate_test",
            template_content="Immediate test prompt",
            category="test",
            is_active=True,
            usage_count=10,  # Ensure it meets evolution criteria
            performance_score=0.5
        )
        evolution_system.db_session.add(template)
        evolution_system.db_session.commit()
        
        # Start service
        background_service.running = True
        
        try:
            # Trigger evolution
            result = await background_service.trigger_immediate_evolution(["immediate_test"])
            
            assert "evolved_templates" in result
            assert "requested_templates" in result
            assert result["requested_templates"] == ["immediate_test"]
        finally:
            background_service.running = False


@pytest.mark.asyncio
async def test_end_to_end_evolution():
    """End-to-end test of the evolution system."""
    # Create in-memory database
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    # Mock OpenAI client
    mock_client = AsyncMock(spec=OpenAIClient)
    mock_client.create_message.return_value = {
        "content": "Improved version of the original prompt with better clarity and structure.",
        "model": "o3-mini",
        "usage": {"input_tokens": 150, "output_tokens": 75}
    }
    
    try:
        # Initialize system
        config = {
            "learning_rate": 0.1,
            "min_samples_for_evolution": 5,
            "min_success_rate": 0.8
        }
        
        evolution_system = PromptEvolutionSystem(session, mock_client, config)
        
        # Create initial template
        template = PromptTemplate(
            template_id="e2e_template",
            template_content="Original prompt: {task}",
            variables=["task"],
            category="test",
            is_active=True
        )
        session.add(template)
        session.commit()
        
        # Record several executions with mixed performance
        for i in range(10):
            execution_id = await evolution_system.record_execution(
                template_id="e2e_template",
                prompt_content=f"Original prompt: task {i}",
                task_type="test_task",
                success=i < 6,  # 60% success rate (below threshold)
                execution_time=1.0 + i * 0.1,
                performance_metrics={"task_number": i}
            )
            
            # Provide feedback for some executions
            if i < 5:
                await evolution_system.integrate_learning(execution_id, {
                    "score": 2.5 + i * 0.2,  # Increasing scores
                    "improvement_areas": ["clarity", "examples"]
                })
        
        # Get initial metrics
        initial_metrics = await evolution_system.get_template_metrics("e2e_template")
        assert initial_metrics.success_rate == 0.6
        
        # Trigger evolution
        new_template_id = await evolution_system.autonomous_prompt_refinement("e2e_template")
        assert new_template_id is not None
        
        # Verify new template was created
        evolved_template = session.query(PromptTemplate).filter_by(
            template_id=new_template_id
        ).first()
        
        assert evolved_template is not None
        assert evolved_template.version == 2
        assert evolved_template.parent_template_id == "e2e_template"
        assert "Improved version" in evolved_template.template_content
        
        # Analyze performance patterns
        patterns = await evolution_system.analyze_performance_patterns(24)
        assert patterns["overall_metrics"]["total_executions"] == 10
        assert "recommendations" in patterns
        
        print("End-to-end evolution test completed successfully!")
        
    finally:
        session.close()


if __name__ == "__main__":
    # Run the end-to-end test
    asyncio.run(test_end_to_end_evolution())