"""
Comprehensive tests for the Prompt Evolution System.

This test suite covers all four primary responsibilities:
1. Autonomous Prompt Refinement
2. Performance Analysis  
3. Template Evolution
4. Learning Integration
"""

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.clients.openai_client import OpenAIClient, OpenAIModel
from src.learning.prompt_evolution import (
    PromptEvolutionSystem,
    PromptTemplate,
    PromptExecution,
    EvolutionHistory,
    PromptMetrics,
    EvolutionStrategy
)
from src.learning.agent_integration import AgentPromptIntegration, EnhancedAgent
from src.learning.evolution_service import EvolutionBackgroundService


class TestPromptEvolutionSystem:
    """Test suite for the core PromptEvolutionSystem class."""
    
    @pytest.fixture
    def mock_db_session(self):
        """Mock database session."""
        session = MagicMock()
        session.query.return_value = session
        session.filter_by.return_value = session
        session.filter.return_value = session
        session.order_by.return_value = session
        session.limit.return_value = session
        session.first.return_value = None
        session.all.return_value = []
        session.count.return_value = 0
        return session
    
    @pytest.fixture
    def mock_openai_client(self):
        """Mock OpenAI client."""
        client = AsyncMock(spec=OpenAIClient)
        client.create_message.return_value = {
            "content": "This is an improved prompt with better clarity and structure.",
            "model": "o3-mini",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        }
        return client
    
    @pytest.fixture
    def evolution_system(self, mock_db_session, mock_openai_client):
        """Create PromptEvolutionSystem instance for testing."""
        config = {
            "learning_rate": 0.1,
            "exploration_rate": 0.2,
            "min_samples_for_evolution": 5,
            "min_success_rate": 0.8,
            "improvement_threshold": 0.3,
            "min_feedback_score": 3.0
        }
        return PromptEvolutionSystem(mock_db_session, mock_openai_client, config)
    
    @pytest.fixture
    def sample_template(self):
        """Sample template for testing."""
        return PromptTemplate(
            id=1,
            template_id="test_template_001",
            template_content="You are a helpful assistant. Please {task_description}",
            variables=["task_description"],
            category="general",
            version=1,
            performance_score=0.75,
            usage_count=10,
            is_active=True
        )
    
    @pytest.fixture
    def sample_executions(self):
        """Sample executions for testing."""
        return [
            PromptExecution(
                execution_id="exec_001",
                template_id="test_template_001",
                prompt_content="You are a helpful assistant. Please write code.",
                task_type="code_generation",
                success=True,
                execution_time=2.5,
                feedback_score=4.0,
                created_at=datetime.utcnow() - timedelta(hours=1)
            ),
            PromptExecution(
                execution_id="exec_002",
                template_id="test_template_001",
                prompt_content="You are a helpful assistant. Please write tests.",
                task_type="test_generation",
                success=False,
                execution_time=5.0,
                error_details="timeout_error",
                created_at=datetime.utcnow() - timedelta(hours=2)
            )
        ]
    
    @pytest.mark.asyncio
    async def test_autonomous_prompt_refinement_success(self, evolution_system, sample_template, mock_db_session):
        """Test successful autonomous prompt refinement."""
        # Setup
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = sample_template
        
        # Mock metrics that indicate refinement is needed
        with patch.object(evolution_system, 'get_template_metrics') as mock_metrics:
            mock_metrics.return_value = PromptMetrics(
                success_rate=0.6,  # Below threshold
                avg_execution_time=3.0,
                avg_feedback_score=2.5,  # Below threshold
                usage_frequency=10,
                error_patterns=["validation_error"],
                improvement_potential=0.4  # Above threshold
            )
            
            # Execute
            result = await evolution_system.autonomous_prompt_refinement("test_template_001")
            
            # Verify
            assert result is not None
            assert result.startswith("test_template_001_v2")
            mock_db_session.add.assert_called()
            mock_db_session.commit.assert_called()
    
    @pytest.mark.asyncio
    async def test_autonomous_prompt_refinement_no_refinement_needed(self, evolution_system, sample_template, mock_db_session):
        """Test refinement when none is needed."""
        # Setup
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = sample_template
        
        # Mock good metrics
        with patch.object(evolution_system, 'get_template_metrics') as mock_metrics:
            mock_metrics.return_value = PromptMetrics(
                success_rate=0.95,  # Above threshold
                avg_execution_time=1.0,
                avg_feedback_score=4.5,  # Above threshold
                usage_frequency=10,
                error_patterns=[],
                improvement_potential=0.1  # Below threshold
            )
            
            # Execute
            result = await evolution_system.autonomous_prompt_refinement("test_template_001")
            
            # Verify - no refinement should occur
            assert result is None
    
    @pytest.mark.asyncio
    async def test_analyze_performance_patterns(self, evolution_system, sample_executions, mock_db_session):
        """Test performance pattern analysis."""
        # Setup
        mock_db_session.query.return_value.filter.return_value.all.return_value = sample_executions
        
        # Execute
        result = await evolution_system.analyze_performance_patterns(24)
        
        # Verify
        assert "overall_metrics" in result
        assert "template_performance" in result
        assert "task_type_patterns" in result
        assert "temporal_patterns" in result
        assert "error_patterns" in result
        assert "recommendations" in result
        
        # Check overall metrics
        overall = result["overall_metrics"]
        assert overall["total_executions"] == 2
        assert overall["success_rate"] == 0.5  # 1 success out of 2
    
    @pytest.mark.asyncio
    async def test_evolve_templates(self, evolution_system, mock_db_session):
        """Test template evolution batch processing."""
        # Setup - mock evolution candidates
        candidates = ["template_001", "template_002", "template_003"]
        
        with patch.object(evolution_system, '_get_evolution_candidates') as mock_candidates:
            mock_candidates.return_value = candidates
            
            with patch.object(evolution_system, 'autonomous_prompt_refinement') as mock_refinement:
                mock_refinement.side_effect = ["template_001_v2", None, "template_003_v2"]
                
                with patch.object(evolution_system, '_schedule_ab_testing') as mock_ab_test:
                    # Execute
                    result = await evolution_system.evolve_templates(batch_size=3)
                    
                    # Verify
                    assert len(result) == 2  # Only 2 successful evolutions
                    assert "template_001_v2" in result
                    assert "template_003_v2" in result
                    assert mock_ab_test.call_count == 2  # A/B testing scheduled for successful evolutions
    
    @pytest.mark.asyncio
    async def test_integrate_learning(self, evolution_system, mock_db_session):
        """Test learning integration from feedback."""
        # Setup
        execution = PromptExecution(
            execution_id="exec_001",
            template_id="test_template_001",
            success=True,
            performance_metrics={}
        )
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = execution
        
        feedback_data = {
            "score": 3.5,
            "improvement_areas": ["clarity", "specificity"],
            "positive_aspects": ["good structure"]
        }
        
        with patch.object(evolution_system, '_update_template_learning') as mock_update:
            # Execute
            result = await evolution_system.integrate_learning("exec_001", feedback_data)
            
            # Verify
            assert result is True
            assert execution.feedback_score == 3.5
            mock_update.assert_called_once()
            mock_db_session.commit.assert_called()
    
    @pytest.mark.asyncio
    async def test_record_execution(self, evolution_system, mock_db_session):
        """Test execution recording."""
        # Execute
        execution_id = await evolution_system.record_execution(
            template_id="test_template_001",
            prompt_content="Test prompt content",
            task_type="test_task",
            success=True,
            execution_time=2.5,
            performance_metrics={"accuracy": 0.95}
        )
        
        # Verify
        assert execution_id.startswith("exec_test_template_001_")
        mock_db_session.add.assert_called()
        mock_db_session.commit.assert_called()
        
        # Check performance history was updated
        assert "test_template_001" in evolution_system.performance_history
        assert len(evolution_system.performance_history["test_template_001"]) == 1
    
    @pytest.mark.asyncio
    async def test_get_template_metrics(self, evolution_system, sample_executions, mock_db_session):
        """Test template metrics calculation."""
        # Setup
        mock_db_session.query.return_value.filter_by.return_value.all.return_value = sample_executions
        
        # Execute
        metrics = await evolution_system.get_template_metrics("test_template_001")
        
        # Verify
        assert isinstance(metrics, PromptMetrics)
        assert metrics.success_rate == 0.5  # 1 success out of 2
        assert metrics.usage_frequency == 2
        assert "timeout_error" in metrics.error_patterns
    
    def test_should_refine_template(self, evolution_system):
        """Test template refinement decision logic."""
        # Test case: low success rate
        metrics_low_success = PromptMetrics(0.5, 2.0, 3.0, 10, [], 0.2)
        assert evolution_system._should_refine_template(metrics_low_success) is True
        
        # Test case: high improvement potential
        metrics_high_potential = PromptMetrics(0.9, 2.0, 4.0, 10, [], 0.4)
        assert evolution_system._should_refine_template(metrics_high_potential) is True
        
        # Test case: low feedback score
        metrics_low_feedback = PromptMetrics(0.9, 2.0, 2.0, 10, [], 0.2)
        assert evolution_system._should_refine_template(metrics_low_feedback) is True
        
        # Test case: all metrics good
        metrics_good = PromptMetrics(0.95, 1.5, 4.5, 10, [], 0.1)
        assert evolution_system._should_refine_template(metrics_good) is False
    
    def test_select_evolution_strategy(self, evolution_system):
        """Test evolution strategy selection."""
        # Test clarity enhancement for low success rate
        metrics_low_success = PromptMetrics(0.5, 2.0, 3.0, 10, [], 0.2)
        strategy = evolution_system._select_evolution_strategy(metrics_low_success)
        assert strategy.name == "clarity_enhancement"
        
        # Test performance tuning for high execution time
        metrics_slow = PromptMetrics(0.8, 15.0, 3.0, 10, [], 0.2)
        strategy = evolution_system._select_evolution_strategy(metrics_slow)
        assert strategy.name == "performance_tuning"
        
        # Test structure refinement for many error patterns
        metrics_errors = PromptMetrics(0.8, 2.0, 3.0, 10, ["error1", "error2", "error3", "error4"], 0.2)
        strategy = evolution_system._select_evolution_strategy(metrics_errors)
        assert strategy.name == "structure_refinement"


class TestAgentPromptIntegration:
    """Test suite for AgentPromptIntegration."""
    
    @pytest.fixture
    def mock_evolution_system(self):
        """Mock evolution system."""
        system = AsyncMock()
        system.record_execution.return_value = "exec_001"
        return system
    
    @pytest.fixture
    def mock_agent_manager(self):
        """Mock agent manager."""
        manager = AsyncMock()
        manager.execute_task.return_value = {
            "success": True,
            "result": "Task completed successfully",
            "metrics": {"accuracy": 0.95}
        }
        return manager
    
    @pytest.fixture
    def integration(self, mock_evolution_system, mock_agent_manager):
        """Create AgentPromptIntegration instance."""
        return AgentPromptIntegration(mock_evolution_system, mock_agent_manager)
    
    @pytest.fixture
    def sample_template_for_integration(self):
        """Sample template for integration testing."""
        return PromptTemplate(
            template_id="integration_template",
            template_content="Execute task: {task_description}",
            version=1
        )
    
    @pytest.mark.asyncio
    async def test_execute_with_evolution_success(self, integration, sample_template_for_integration):
        """Test successful task execution with evolution tracking."""
        # Setup
        with patch.object(integration, '_get_active_template') as mock_get_template:
            mock_get_template.return_value = sample_template_for_integration
            
            # Execute
            result = await integration.execute_with_evolution(
                agent_id="agent_001",
                task_type="code_generation",
                template_id="integration_template",
                variables={"task_description": "write a function"}
            )
            
            # Verify
            assert result["success"] is True
            assert "evolution_tracking" in result
            assert result["evolution_tracking"]["execution_id"] == "exec_001"
            assert result["evolution_tracking"]["template_id"] == "integration_template"
    
    @pytest.mark.asyncio
    async def test_provide_feedback(self, integration):
        """Test feedback provision."""
        feedback_data = {
            "score": 4.0,
            "improvement_areas": ["clarity"],
            "positive_aspects": ["good structure"]
        }
        
        # Execute
        result = await integration.provide_feedback("exec_001", feedback_data)
        
        # Verify
        integration.evolution_system.integrate_learning.assert_called_once_with("exec_001", feedback_data)
    
    @pytest.mark.asyncio
    async def test_get_template_recommendations(self, integration):
        """Test template recommendations."""
        # Setup mock database queries
        mock_templates = [
            MagicMock(template_id="template_001", is_active=True),
            MagicMock(template_id="template_002", is_active=True)
        ]
        
        integration.evolution_system.db_session.query.return_value.filter_by.return_value.all.return_value = mock_templates
        integration.evolution_system.db_session.query.return_value.filter_by.return_value.limit.return_value.all.return_value = [MagicMock()]
        
        with patch.object(integration.evolution_system, 'get_template_metrics') as mock_metrics:
            mock_metrics.return_value = PromptMetrics(0.9, 2.0, 4.0, 10, [], 0.1)
            
            # Execute
            result = await integration.get_template_recommendations("code_generation")
            
            # Verify
            assert "recommended_templates" in result
            assert "task_type" in result
            assert result["task_type"] == "code_generation"


class TestEvolutionBackgroundService:
    """Test suite for EvolutionBackgroundService."""
    
    @pytest.fixture
    def mock_evolution_system(self):
        """Mock evolution system for service testing."""
        system = AsyncMock()
        system.evolve_templates.return_value = ["template_001_v2", "template_002_v2"]
        system.analyze_performance_patterns.return_value = {
            "recommendations": ["Improve template clarity"],
            "template_performance": {
                "template_001": {"success_rate": 0.4, "executions": 10}
            }
        }
        return system
    
    @pytest.fixture
    def service_config(self):
        """Service configuration for testing."""
        return {
            "evolution_interval_hours": 0.01,  # Very short for testing
            "analysis_interval_hours": 0.005,
            "monitoring_interval_minutes": 0.1,
            "evolution_batch_size": 2,
            "max_concurrent_evolutions": 2
        }
    
    @pytest.fixture
    def background_service(self, mock_evolution_system, service_config):
        """Create EvolutionBackgroundService instance."""
        return EvolutionBackgroundService(mock_evolution_system, service_config)
    
    @pytest.mark.asyncio
    async def test_trigger_immediate_evolution(self, background_service):
        """Test immediate evolution trigger."""
        # Start service
        background_service.running = True
        
        # Execute
        result = await background_service.trigger_immediate_evolution(["template_001", "template_002"])
        
        # Verify
        assert "evolved_templates" in result
        assert "requested_templates" in result
        assert result["requested_templates"] == ["template_001", "template_002"]
    
    def test_get_service_status(self, background_service):
        """Test service status retrieval."""
        # Execute
        status = background_service.get_service_status()
        
        # Verify
        assert "running" in status
        assert "uptime_seconds" in status
        assert "active_evolutions" in status
        assert "stats" in status
        assert "config" in status
    
    @pytest.mark.asyncio
    async def test_run_evolution_cycle(self, background_service):
        """Test evolution cycle execution."""
        # Execute
        result = await background_service._run_evolution_cycle()
        
        # Verify
        assert "evolved_templates" in result
        assert result["count"] == 2
        assert background_service.evolution_system.evolve_templates.called


class TestOpenAIClient:
    """Test suite for OpenAIClient."""
    
    @pytest.fixture
    def mock_openai_response(self):
        """Mock OpenAI API response."""
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = "Test response content"
        response.choices[0].finish_reason = "stop"
        response.usage.prompt_tokens = 100
        response.usage.completion_tokens = 50
        response.usage.total_tokens = 150
        return response
    
    @pytest.fixture
    def openai_client(self):
        """Create OpenAI client for testing."""
        from src.clients.openai_client import OpenAIClient
        return OpenAIClient("test-api-key", {"max_tokens": 1000})
    
    @pytest.mark.asyncio
    async def test_create_message(self, openai_client, mock_openai_response):
        """Test message creation."""
        with patch.object(openai_client.client.chat.completions, 'create') as mock_create:
            mock_create.return_value = mock_openai_response
            
            messages = [{"role": "user", "content": "Test message"}]
            result = await openai_client.create_message(messages)
            
            assert result["content"] == "Test response content"
            assert result["usage"]["total_tokens"] == 150
            mock_create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_evolution_prompt(self, openai_client, mock_openai_response):
        """Test evolution prompt creation."""
        with patch.object(openai_client, 'create_message') as mock_create:
            mock_create.return_value = {"content": "Improved prompt content"}
            
            result = await openai_client.create_evolution_prompt(
                original_prompt="Original prompt",
                strategy="clarity_enhancement",
                metrics={"success_rate": 0.6, "avg_execution_time": 3.0, "error_patterns": ["timeout"]}
            )
            
            assert result == "Improved prompt content"
            mock_create.assert_called_once()
    
    def test_usage_stats(self, openai_client):
        """Test usage statistics tracking."""
        stats = openai_client.get_usage_stats()
        
        assert "total_requests" in stats
        assert "total_tokens" in stats
        assert "total_cost" in stats
        assert "model_usage" in stats
        
        # Test reset
        openai_client.reset_usage_stats()
        stats_after_reset = openai_client.get_usage_stats()
        assert stats_after_reset["total_requests"] == 0


@pytest.mark.integration
class TestPromptEvolutionIntegration:
    """Integration tests for the complete system."""
    
    @pytest.mark.asyncio
    async def test_full_evolution_workflow(self):
        """Test the complete evolution workflow from execution to refinement."""
        # This would be a comprehensive integration test
        # involving real database and API calls (mocked for CI/CD)
        pass
    
    @pytest.mark.asyncio
    async def test_concurrent_evolution_safety(self):
        """Test that concurrent evolutions don't conflict."""
        # Test concurrent access to templates and evolution processes
        pass
    
    @pytest.mark.asyncio
    async def test_error_recovery(self):
        """Test system recovery from various error conditions."""
        # Test recovery from database errors, API failures, etc.
        pass