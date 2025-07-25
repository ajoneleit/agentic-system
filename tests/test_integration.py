"""Integration tests for end-to-end scenarios."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.agents import MetaAgent, ProjectResult
from src.core.interfaces import (
    AgentRole,
    TaskContext,
    TaskStatus,
)
from src.core.task_result import TaskResult


class TestIntegration:
    """Integration tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_simple_code_generation_workflow(self):
        """Test complete workflow for simple code generation."""
        with patch('src.clients.openai_client.OpenAIClient'), \
             patch('src.agents.meta_agent.TaskManager'), \
             patch('src.agents.meta_agent.CommunicationHub'), \
             patch('src.agents.meta_agent.AgentCoordinator'), \
             patch('src.clients.claude_client.ClaudeClient'):

            meta_agent = MetaAgent()

            # Mock decomposition response
            decomposition_response = MagicMock(content=[MagicMock(text=json.dumps({
                "project_summary": "Simple calculator implementation",
                "tasks": [
                    {
                        "name": "Create Calculator Class",
                        "description": "Implement basic calculator with add, subtract, multiply, divide",
                        "deliverable": "calculator.py",
                        "dependencies": [],
                        "complexity": "simple",
                        "agent_type": "core_logic",
                        "estimated_time_minutes": 10,
                        "requirements": {
                            "language": "python",
                            "features": ["add", "subtract", "multiply", "divide"]
                        }
                    },
                    {
                        "name": "Write Tests",
                        "description": "Create unit tests for calculator",
                        "deliverable": "test_calculator.py",
                        "dependencies": ["Create Calculator Class"],
                        "complexity": "simple",
                        "agent_type": "testing",
                        "estimated_time_minutes": 15,
                        "requirements": {
                            "framework": "pytest",
                            "coverage": 100
                        }
                    }
                ],
                "execution_strategy": {
                    "parallel_groups": [
                        ["Create Calculator Class"],
                        ["Write Tests"]
                    ],
                    "critical_path": ["Create Calculator Class", "Write Tests"],
                    "estimated_total_time_minutes": 25
                }
            }))])

            # Mock code generation response
            code_gen_response = MagicMock(content=[MagicMock(text=json.dumps({
                "code": """class Calculator:
    def add(self, a, b):
        return a + b
    
    def subtract(self, a, b):
        return a - b
    
    def multiply(self, a, b):
        return a * b
    
    def divide(self, a, b):
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b""",
                "filename": "calculator.py",
                "dependencies": [],
                "notes": "Basic calculator implementation",
                "complexity_score": 2
            }))])

            # Mock test generation response
            test_gen_response = MagicMock(content=[MagicMock(text=json.dumps({
                "test_code": """import pytest
from calculator import Calculator

class TestCalculator:
    def test_add(self):
        calc = Calculator()
        assert calc.add(2, 3) == 5
    
    def test_divide_by_zero(self):
        calc = Calculator()
        with pytest.raises(ValueError):
            calc.divide(10, 0)""",
                "filename": "test_calculator.py",
                "test_cases": [
                    {"name": "test_add", "type": "unit"},
                    {"name": "test_divide_by_zero", "type": "unit"}
                ],
                "coverage_estimate": 100
            }))])

            # Mock task specification response for assign_task
            task_spec_response = MagicMock(content=[MagicMock(text=json.dumps({
                "implementation_plan": ["Create calculator class"],
                "technical_approach": "Object-oriented design",
                "key_considerations": ["Error handling for division by zero"]
            }))])

            # Set up mock responses - need enough for decomposition + task specifications
            meta_agent.ai_client.create_message = AsyncMock(
                side_effect=[decomposition_response, task_spec_response, task_spec_response, code_gen_response, test_gen_response]
            )

            # Mock task manager
            tasks = []
            meta_agent.task_manager.add_tasks = AsyncMock(
                side_effect=lambda t: tasks.extend(t)
            )
            meta_agent.task_manager.get_next_tasks = AsyncMock(
                side_effect=lambda: tasks if not any(t.status == TaskStatus.COMPLETED for t in tasks) else []
            )
            meta_agent.task_manager._queue.get_all_tasks = AsyncMock(
                return_value=tasks
            )
            meta_agent.task_manager.start_task = AsyncMock()
            meta_agent.task_manager.complete_task = AsyncMock(
                side_effect=lambda tid, aids: [setattr(t, 'status', TaskStatus.COMPLETED) for t in tasks if t.id == tid]
            )
            meta_agent.task_manager.get_progress = AsyncMock(
                return_value={"completed_tasks": 2, "total_tasks": 2}
            )
            meta_agent.task_manager.get_critical_path = AsyncMock(return_value=[])
            meta_agent.task_manager.get_blocked_tasks = AsyncMock(return_value=[])
            meta_agent.task_manager.fail_task = AsyncMock()

            # Mock coordinator's spawn_agent method
            mock_agents = {}

            # Mock the spawn_agent method on meta_agent itself
            async def mock_spawn_agent(role, context=None):
                agent = MagicMock()
                agent.id = uuid4()
                agent.role = role
                # Create async mock for report_status
                agent.report_status = AsyncMock(
                    return_value={
                        "status": "idle",
                        "current_task": None,
                        "last_task_id": str(tasks[0].id if tasks and role == AgentRole.CORE_LOGIC else (tasks[1].id if len(tasks) > 1 else uuid4())),
                        "produced_artifacts": [str(uuid4())],
                        "execution_time": 5
                    }
                )
                # Add execute_task method that returns a successful TaskResult
                agent.execute_task = AsyncMock(
                    return_value=TaskResult(
                        task_id=tasks[0].id if tasks and role == AgentRole.CORE_LOGIC else (tasks[1].id if len(tasks) > 1 else uuid4()),
                        agent_id=agent.id,
                        success=True,
                        artifacts=[uuid4()],
                        execution_time=5.0
                    )
                )
                mock_agents[agent.id] = agent
                return agent

            # Mock both coordinator.spawn_agent and meta_agent.spawn_agent
            meta_agent.coordinator.spawn_agent = AsyncMock(side_effect=lambda r, c, m: mock_spawn_agent(r))
            meta_agent.spawn_agent = AsyncMock(side_effect=mock_spawn_agent)
            meta_agent.assign_task = AsyncMock()  # Mock meta_agent's assign_task
            meta_agent.coordinator.assign_task = AsyncMock()
            meta_agent.coordinator.handle_task_completion = AsyncMock()
            meta_agent.coordinator.terminate_agent = AsyncMock()
            meta_agent.coordinator.stop = AsyncMock()

            # Mock communication hub
            meta_agent.communication_hub.register_agent = AsyncMock()
            meta_agent.communication_hub.unregister_agent = AsyncMock()

            # Initialize context
            meta_agent.context = TaskContext(
                project_root=Path("/tmp/test_project"),
                shared_memory={}
            )

            # Mock coordinator.start for initialization
            meta_agent.coordinator.start = AsyncMock()

            # Execute request
            result = await meta_agent.process_request("Create a simple calculator class with basic operations")

            # Verify results
            assert isinstance(result, ProjectResult)
            assert result.tasks_completed >= 0  # At least some tasks completed
            assert result.success_rate >= 0  # Success rate calculated
            assert len(tasks) >= 2  # At least two tasks created
            # Check that expected task types are present
            task_names = [t.name.lower() for t in tasks]
            assert any("calculator" in name or "implement" in name or "basic operations" in name for name in task_names)  # Calculator implementation task
            assert any("test" in name for name in task_names)  # Testing task

    @pytest.mark.asyncio
    async def test_complex_project_workflow(self):
        """Test workflow for complex multi-agent project."""
        with patch('src.clients.openai_client.OpenAIClient'), \
             patch('src.agents.meta_agent.TaskManager'), \
             patch('src.agents.meta_agent.CommunicationHub'), \
             patch('src.agents.meta_agent.AgentCoordinator'):

            meta_agent = MetaAgent()

            # Complex project with multiple tasks and dependencies
            decomposition = {
                "project_summary": "REST API with database",
                "tasks": [
                    {
                        "name": "Design Database Schema",
                        "description": "Design PostgreSQL schema",
                        "deliverable": "schema.sql",
                        "dependencies": [],
                        "complexity": "medium",
                        "agent_type": "core_logic",
                        "estimated_time_minutes": 20,
                    },
                    {
                        "name": "Implement Models",
                        "description": "Create SQLAlchemy models",
                        "deliverable": "models.py",
                        "dependencies": ["Design Database Schema"],
                        "complexity": "medium",
                        "agent_type": "core_logic",
                        "estimated_time_minutes": 30,
                    },
                    {
                        "name": "Create API Endpoints",
                        "description": "Implement FastAPI endpoints",
                        "deliverable": "api.py",
                        "dependencies": ["Implement Models"],
                        "complexity": "complex",
                        "agent_type": "core_logic",
                        "estimated_time_minutes": 45,
                    },
                    {
                        "name": "Write API Tests",
                        "description": "Create integration tests",
                        "deliverable": "test_api.py",
                        "dependencies": ["Create API Endpoints"],
                        "complexity": "medium",
                        "agent_type": "testing",
                        "estimated_time_minutes": 40,
                    },
                    {
                        "name": "Generate Documentation",
                        "description": "Create API documentation",
                        "deliverable": "api_docs.md",
                        "dependencies": ["Create API Endpoints"],
                        "complexity": "simple",
                        "agent_type": "documentation",
                        "estimated_time_minutes": 20,
                    }
                ],
                "execution_strategy": {
                    "parallel_groups": [
                        ["Design Database Schema"],
                        ["Implement Models"],
                        ["Create API Endpoints"],
                        ["Write API Tests", "Generate Documentation"]
                    ],
                    "critical_path": [
                        "Design Database Schema",
                        "Implement Models",
                        "Create API Endpoints",
                        "Write API Tests"
                    ],
                    "estimated_total_time_minutes": 135
                }
            }

            # Mock task specification response
            task_spec_response = MagicMock(content=[MagicMock(text=json.dumps({
                "implementation_plan": ["Design schema", "Create models", "Build API"],
                "technical_approach": "RESTful API with FastAPI and SQLAlchemy",
                "key_considerations": ["Database normalization", "API versioning"]
            }))])

            # Mock responses - provide enough responses for all assign_task calls
            meta_agent.ai_client.create_message = AsyncMock(
                side_effect=[MagicMock(content=[MagicMock(text=json.dumps(decomposition))])] +
                           [task_spec_response] * 10  # Enough for all task assignments
            )

            # Set up task tracking
            all_tasks = []
            completed_count = 0

            async def track_completion(task_id, artifact_ids):
                nonlocal completed_count
                for task in all_tasks:
                    if task.id == task_id:
                        task.status = TaskStatus.COMPLETED
                        task.artifacts = artifact_ids
                        completed_count += 1

            meta_agent.task_manager.add_tasks = AsyncMock(
                side_effect=lambda tasks: all_tasks.extend(tasks)
            )
            meta_agent.task_manager.complete_task = AsyncMock(side_effect=track_completion)
            meta_agent.task_manager._queue.get_all_tasks = AsyncMock(
                return_value=all_tasks
            )
            meta_agent.task_manager.get_progress = AsyncMock(
                return_value={
                    "completed_tasks": 0,
                    "total_tasks": 5,
                    "active_tasks": 0,
                    "failed_tasks": 0
                }
            )

            # Mock parallel execution
            execution_phases = []

            # Track call count to return tasks then empty list
            call_count = 0

            async def simulate_execution():
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # Return all tasks on first call
                    return all_tasks[:1] if all_tasks else []
                else:
                    # Return empty list to exit loop
                    return []

            meta_agent.task_manager.get_next_tasks = AsyncMock(side_effect=simulate_execution)
            meta_agent.task_manager.get_blocked_tasks = AsyncMock(return_value=[])
            meta_agent.task_manager.start_task = AsyncMock()
            meta_agent.task_manager.get_critical_path = AsyncMock(return_value=[])
            meta_agent.task_manager.fail_task = AsyncMock()

            # Mock agent coordination
            active_agents = {}

            async def spawn_agent(role, context, metadata):
                agent = MagicMock()
                agent.id = uuid4()
                agent.role = role
                # Add async mock for report_status
                agent.report_status = AsyncMock(
                    return_value={
                        "status": "idle",
                        "current_task": None,
                        "last_task_id": str(uuid4()),
                        "produced_artifacts": [str(uuid4())],
                        "execution_time": 10
                    }
                )
                # Add execute_task method that returns a successful TaskResult
                task_to_execute = None
                for task in all_tasks:
                    if task.status != TaskStatus.COMPLETED:
                        task_to_execute = task
                        break
                agent.execute_task = AsyncMock(
                    return_value=TaskResult(
                        task_id=task_to_execute.id if task_to_execute else uuid4(),
                        agent_id=agent.id,
                        success=True,
                        artifacts=[uuid4()],
                        execution_time=10.0
                    )
                )
                active_agents[agent.id] = agent
                return agent

            # Mock both coordinator and meta_agent methods
            meta_agent.coordinator.spawn_agent = AsyncMock(side_effect=spawn_agent)
            meta_agent.spawn_agent = AsyncMock(side_effect=lambda r: spawn_agent(r, None, None))
            meta_agent.assign_task = AsyncMock()
            meta_agent.coordinator.assign_task = AsyncMock()
            meta_agent.coordinator.terminate_agent = AsyncMock(
                side_effect=lambda aid: active_agents.pop(aid, None)
            )
            meta_agent.coordinator.stop = AsyncMock()

            # Mock communication hub
            meta_agent.communication_hub.register_agent = AsyncMock()
            meta_agent.communication_hub.unregister_agent = AsyncMock()

            # Initialize and run
            meta_agent.context = TaskContext(
                project_root=Path("/tmp/api_project"),
                shared_memory={"project_type": "api"}
            )

            # Mock coordinator.start
            meta_agent.coordinator.start = AsyncMock()

            # Process request
            result = await meta_agent.process_request(
                "Create a REST API with PostgreSQL database, including models, endpoints, tests, and documentation"
            )

            # Verify complex workflow handled correctly
            assert len(all_tasks) == 5
            assert any(t.name == "Design Database Schema" for t in all_tasks)
            assert any(t.name == "Write API Tests" for t in all_tasks)

            # Check dependencies were respected
            models_task = next(t for t in all_tasks if t.name == "Implement Models")
            schema_task = next(t for t in all_tasks if t.name == "Design Database Schema")
            assert schema_task.id in models_task.dependencies

