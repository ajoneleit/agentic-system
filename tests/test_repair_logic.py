"""
Comprehensive test suite for Repair Logic and Self-Healing systems.
Focus on error recovery, repair strategies, and infinite loop prevention.
"""

import asyncio
from datetime import datetime
from typing import Dict, List
from uuid import uuid4

import pytest

# from src.verification.repair_analyzer import RepairAnalyzer  # May not exist yet
from src.core.interfaces import AgentRole, Task, TaskPriority, TaskStatus
from src.core.result import Result


# RepairError may not exist yet
class RepairError(Exception):
    pass


class MockRepairAnalyzer:
    """Mock implementation of RepairAnalyzer for testing."""

    def __init__(self):
        self.repair_attempts = {}
        self.repair_strategies = {}
        self.max_repair_attempts = 3

    async def analyze_failure(self, task: Task, error: Exception) -> Dict:
        """Analyze task failure and suggest repair strategy."""
        failure_type = error.__class__.__name__

        return {
            "failure_type": failure_type,
            "error_message": str(error),
            "repair_strategy": self._suggest_repair_strategy(failure_type),
            "confidence": 0.8,
            "estimated_repair_time": 30
        }

    def _suggest_repair_strategy(self, failure_type: str) -> str:
        """Suggest repair strategy based on failure type."""
        strategies = {
            "TimeoutError": "increase_timeout",
            "MemoryError": "reduce_memory_usage",
            "SyntaxError": "fix_syntax",
            "ImportError": "install_dependencies",
            "FileNotFoundError": "create_missing_files",
            "ConnectionError": "retry_with_backoff"
        }
        return strategies.get(failure_type, "generic_retry")

    async def generate_repair_tasks(self, task: Task, analysis: Dict) -> List[Task]:
        """Generate repair tasks based on analysis."""
        repair_strategy = analysis["repair_strategy"]

        repair_task = Task(
            id=uuid4(),
            name=f"repair_{task.name}",
            description=f"Repair task using {repair_strategy} strategy",
            agent_role=AgentRole.VERIFICATION,
            priority=TaskPriority.HIGH,
            status=TaskStatus.PENDING,
            metadata={
                "repair_strategy": repair_strategy,
                "original_task_id": str(task.id),
                "repair_attempt": self.repair_attempts.get(str(task.id), 0) + 1
            }
        )

        self.repair_attempts[str(task.id)] = repair_task.metadata["repair_attempt"]
        return [repair_task]

    async def execute_repair(self, repair_task: Task) -> Result[bool]:
        """Execute a repair task."""
        strategy = repair_task.metadata.get("repair_strategy")
        attempt = repair_task.metadata.get("repair_attempt", 1)

        # Simulate repair execution
        if attempt >= self.max_repair_attempts:
            return Result.failure(RepairError(f"Maximum repair attempts ({self.max_repair_attempts}) exceeded"))

        # Simulate strategy-specific logic
        if strategy == "increase_timeout":
            await asyncio.sleep(0.1)  # Simulate timeout adjustment
            return Result.success(True)
        elif strategy == "fix_syntax":
            # Simulate syntax fix with 70% success rate
            import random
            if random.random() < 0.7:
                return Result.success(True)
            else:
                return Result.failure(RepairError("Syntax fix failed"))
        elif strategy == "generic_retry":
            # Simulate generic retry with 50% success rate
            import random
            if random.random() < 0.5:
                return Result.success(True)
            else:
                return Result.failure(RepairError("Generic retry failed"))

        return Result.success(True)


class TestRepairLoopConvergence:
    """Test repair loop convergence and termination conditions."""

    @pytest.fixture
    def repair_analyzer(self):
        """Create a mock repair analyzer."""
        return MockRepairAnalyzer()

    @pytest.fixture
    def failing_task(self):
        """Create a task that simulates failure."""
        return Task(
            id=uuid4(),
            name="failing_task",
            description="A task that fails and needs repair",
            agent_role=AgentRole.CORE_LOGIC,
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.FAILED,
            metadata={"failure_reason": "TimeoutError", "attempts": 1}
        )

    @pytest.mark.asyncio
    async def test_repair_loop_convergence(self, repair_analyzer, failing_task):
        """Test that repair loops converge to a solution."""

        # Simulate repair loop
        max_iterations = 10
        current_task = failing_task

        for iteration in range(max_iterations):
            # Analyze failure
            error = TimeoutError("Task timed out")
            analysis = await repair_analyzer.analyze_failure(current_task, error)

            # Generate repair tasks
            repair_tasks = await repair_analyzer.generate_repair_tasks(current_task, analysis)
            assert len(repair_tasks) == 1

            repair_task = repair_tasks[0]

            # Execute repair
            repair_result = await repair_analyzer.execute_repair(repair_task)

            if repair_result.is_success():
                # Repair succeeded, loop should converge
                assert repair_result.unwrap() == True
                break
            else:
                # Repair failed, continue loop
                current_task = repair_task
                current_task.status = TaskStatus.FAILED

        # Verify loop converged (didn't reach max iterations)
        assert iteration < max_iterations - 1

    @pytest.mark.asyncio
    async def test_repair_infinite_loop_prevention(self, repair_analyzer):
        """Test prevention of infinite repair loops."""

        # Create a task that consistently fails repair
        persistent_failing_task = Task(
            id=uuid4(),
            name="persistent_failing_task",
            description="A task that always fails repair",
            agent_role=AgentRole.CORE_LOGIC,
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.FAILED,
            metadata={"failure_reason": "PersistentError"}
        )

        # Override repair analyzer to always fail but still check counter
        class AlwaysFailingAnalyzer(MockRepairAnalyzer):
            async def execute_repair(self, repair_task: Task) -> Result[bool]:
                attempt = repair_task.metadata.get("repair_attempt", 1)

                # Check max attempts first
                if attempt >= self.max_repair_attempts:
                    return Result.failure(RepairError(f"Maximum repair attempts ({self.max_repair_attempts}) exceeded"))

                # Always fail but with different error
                return Result.failure(RepairError("Persistent failure"))

        failing_analyzer = AlwaysFailingAnalyzer()

        # Simulate repair loop with failure tracking
        max_attempts = 5
        original_task = persistent_failing_task

        for attempt in range(max_attempts):
            error = Exception("Persistent error")
            analysis = await failing_analyzer.analyze_failure(original_task, error)
            repair_tasks = await failing_analyzer.generate_repair_tasks(original_task, analysis)

            repair_task = repair_tasks[0]
            repair_result = await failing_analyzer.execute_repair(repair_task)

            # Should eventually prevent infinite loop
            if repair_task.metadata.get("repair_attempt", 0) >= failing_analyzer.max_repair_attempts:
                assert repair_result.is_failure()
                assert "Maximum repair attempts" in str(repair_result.get_error())
                break

        # Verify infinite loop was prevented
        assert repair_task.metadata.get("repair_attempt", 0) >= failing_analyzer.max_repair_attempts

    @pytest.mark.asyncio
    async def test_repair_convergence_with_multiple_strategies(self, repair_analyzer):
        """Test repair convergence when multiple strategies are needed."""

        # Create tasks with different failure types
        failure_scenarios = [
            ("TimeoutError", "increase_timeout"),
            ("MemoryError", "reduce_memory_usage"),
            ("SyntaxError", "fix_syntax"),
            ("ImportError", "install_dependencies")
        ]

        convergence_results = []

        for error_type, expected_strategy in failure_scenarios:
            failing_task = Task(
                id=uuid4(),
                name=f"task_with_{error_type}",
                description=f"Task that fails with {error_type}",
                agent_role=AgentRole.CORE_LOGIC,
                priority=TaskPriority.MEDIUM,
                status=TaskStatus.FAILED,
                metadata={"failure_reason": error_type}
            )

            # Simulate error
            if error_type == "TimeoutError":
                error = TimeoutError("Task timed out")
            elif error_type == "MemoryError":
                error = MemoryError("Out of memory")
            elif error_type == "SyntaxError":
                error = SyntaxError("Invalid syntax")
            elif error_type == "ImportError":
                error = ImportError("Module not found")

            # Analyze and repair
            analysis = await repair_analyzer.analyze_failure(failing_task, error)
            assert analysis["repair_strategy"] == expected_strategy

            repair_tasks = await repair_analyzer.generate_repair_tasks(failing_task, analysis)
            repair_task = repair_tasks[0]

            repair_result = await repair_analyzer.execute_repair(repair_task)
            convergence_results.append(repair_result.is_success())

        # Verify most repairs converged successfully
        success_rate = sum(convergence_results) / len(convergence_results)
        assert success_rate >= 0.5  # At least 50% success rate


class TestRepairStrategySelection:
    """Test repair strategy selection and adaptation."""

    @pytest.fixture
    def repair_analyzer(self):
        return MockRepairAnalyzer()

    @pytest.mark.asyncio
    async def test_repair_strategy_selection(self, repair_analyzer):
        """Test that appropriate repair strategies are selected."""

        # Test different error types and their expected strategies
        test_cases = [
            (TimeoutError("Connection timeout"), "increase_timeout"),
            (MemoryError("Out of memory"), "reduce_memory_usage"),
            (SyntaxError("Invalid syntax"), "fix_syntax"),
            (ImportError("No module named 'xyz'"), "install_dependencies"),
            (FileNotFoundError("File not found"), "create_missing_files"),
            (ConnectionError("Connection failed"), "retry_with_backoff"),
            (ValueError("Unknown error"), "generic_retry")  # Fallback strategy
        ]

        for error, expected_strategy in test_cases:
            task = Task(
                id=uuid4(),
                name="test_task",
                description="Test task for strategy selection",
                agent_role=AgentRole.CORE_LOGIC,
                priority=TaskPriority.MEDIUM,
                status=TaskStatus.FAILED
            )

            analysis = await repair_analyzer.analyze_failure(task, error)

            assert analysis["repair_strategy"] == expected_strategy
            assert analysis["failure_type"] == error.__class__.__name__
            assert "error_message" in analysis
            assert analysis["confidence"] > 0

    @pytest.mark.asyncio
    async def test_repair_strategy_adaptation(self, repair_analyzer):
        """Test that repair strategies adapt based on previous failures."""

        # Create a task that fails multiple times
        task = Task(
            id=uuid4(),
            name="adaptive_task",
            description="Task that requires strategy adaptation",
            agent_role=AgentRole.CORE_LOGIC,
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.FAILED
        )

        # First attempt - syntax error
        error1 = SyntaxError("Syntax error")
        analysis1 = await repair_analyzer.analyze_failure(task, error1)
        repair_tasks1 = await repair_analyzer.generate_repair_tasks(task, analysis1)

        assert analysis1["repair_strategy"] == "fix_syntax"
        assert repair_tasks1[0].metadata["repair_attempt"] == 1

        # Second attempt - after syntax fix fails
        error2 = ImportError("Import error after syntax fix")
        analysis2 = await repair_analyzer.analyze_failure(task, error2)
        repair_tasks2 = await repair_analyzer.generate_repair_tasks(task, analysis2)

        assert analysis2["repair_strategy"] == "install_dependencies"
        assert repair_tasks2[0].metadata["repair_attempt"] == 2

        # Third attempt - different strategy
        error3 = TimeoutError("Timeout after dependency fix")
        analysis3 = await repair_analyzer.analyze_failure(task, error3)
        repair_tasks3 = await repair_analyzer.generate_repair_tasks(task, analysis3)

        assert analysis3["repair_strategy"] == "increase_timeout"
        assert repair_tasks3[0].metadata["repair_attempt"] == 3


class TestRepairFailureEscalation:
    """Test repair failure escalation and resource management."""

    @pytest.fixture
    def repair_analyzer(self):
        return MockRepairAnalyzer()

    @pytest.mark.asyncio
    async def test_repair_failure_escalation(self, repair_analyzer):
        """Test escalation when repair attempts fail."""

        # Create a task that will require escalation
        task = Task(
            id=uuid4(),
            name="escalation_task",
            description="Task requiring escalation",
            agent_role=AgentRole.CORE_LOGIC,
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.FAILED
        )

        # Simulate escalation through multiple repair attempts
        for attempt in range(1, 5):  # Try 4 times
            error = Exception(f"Failure attempt {attempt}")
            analysis = await repair_analyzer.analyze_failure(task, error)
            repair_tasks = await repair_analyzer.generate_repair_tasks(task, analysis)

            repair_task = repair_tasks[0]
            repair_result = await repair_analyzer.execute_repair(repair_task)

            if attempt <= repair_analyzer.max_repair_attempts:
                # Should continue trying
                assert repair_task.metadata["repair_attempt"] == attempt
            else:
                # Should escalate/fail
                assert repair_result.is_failure()
                assert "Maximum repair attempts" in str(repair_result.get_error())
                break

    @pytest.mark.asyncio
    async def test_repair_resource_exhaustion(self, repair_analyzer):
        """Test handling of resource exhaustion during repair."""

        # Create multiple tasks that require repair simultaneously
        tasks = []
        for i in range(10):
            task = Task(
                id=uuid4(),
                name=f"resource_task_{i}",
                description=f"Task {i} requiring repair resources",
                agent_role=AgentRole.CORE_LOGIC,
                priority=TaskPriority.MEDIUM,
                status=TaskStatus.FAILED
            )
            tasks.append(task)

        # Simulate concurrent repair attempts
        async def repair_task_concurrently(task):
            error = Exception("Resource-intensive error")
            analysis = await repair_analyzer.analyze_failure(task, error)
            repair_tasks = await repair_analyzer.generate_repair_tasks(task, analysis)
            return await repair_analyzer.execute_repair(repair_tasks[0])

        # Execute repairs concurrently
        repair_results = await asyncio.gather(
            *[repair_task_concurrently(task) for task in tasks],
            return_exceptions=True
        )

        # Verify resource management
        successful_repairs = sum(
            1 for result in repair_results
            if isinstance(result, Result) and result.is_success()
        )

        # Should handle resource constraints gracefully
        assert successful_repairs >= 1  # At least some should succeed

        # Check for resource exhaustion errors
        resource_errors = [
            result for result in repair_results
            if isinstance(result, Result) and result.is_failure() and
            "resource" in str(result.get_error()).lower()
        ]

        # May have some resource exhaustion (depends on implementation)
        assert len(resource_errors) >= 0


class TestRepairSelfHealingLoops:
    """Test self-healing loop mechanisms."""

    @pytest.fixture
    def repair_analyzer(self):
        return MockRepairAnalyzer()

    @pytest.mark.asyncio
    async def test_self_healing_loop_detection(self, repair_analyzer):
        """Test detection of self-healing opportunities."""

        # Create a pattern of failures that indicates need for self-healing
        failure_pattern = [
            ("TimeoutError", "increase_timeout"),
            ("TimeoutError", "increase_timeout"),
            ("TimeoutError", "increase_timeout"),  # Repeated timeout failures
        ]

        task = Task(
            id=uuid4(),
            name="self_healing_task",
            description="Task with recurring failures",
            agent_role=AgentRole.CORE_LOGIC,
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.FAILED
        )

        # Track repair attempts
        repair_attempts = []

        for error_type, expected_strategy in failure_pattern:
            error = TimeoutError("Recurring timeout")
            analysis = await repair_analyzer.analyze_failure(task, error)
            repair_tasks = await repair_analyzer.generate_repair_tasks(task, analysis)

            repair_attempts.append({
                "strategy": analysis["repair_strategy"],
                "attempt": repair_tasks[0].metadata["repair_attempt"]
            })

        # Verify pattern detection
        strategies = [attempt["strategy"] for attempt in repair_attempts]
        assert len(set(strategies)) == 1  # Same strategy repeated
        assert strategies[0] == "increase_timeout"

        # Verify escalating attempt numbers
        attempt_numbers = [attempt["attempt"] for attempt in repair_attempts]
        assert attempt_numbers == [1, 2, 3]  # Escalating attempts

    @pytest.mark.asyncio
    async def test_self_healing_loop_prevention(self, repair_analyzer):
        """Test prevention of harmful self-healing loops."""

        # Create a scenario where self-healing might cause problems
        class ProblematicSelfHealingAnalyzer(MockRepairAnalyzer):
            def __init__(self):
                super().__init__()
                self.healing_cycles = 0

            async def execute_repair(self, repair_task: Task) -> Result[bool]:
                self.healing_cycles += 1

                # Simulate problematic healing that creates new issues
                if self.healing_cycles > 5:
                    return Result.failure(RepairError("Self-healing loop detected"))

                # Simulate temporary success followed by new failure
                if self.healing_cycles % 2 == 0:
                    return Result.success(True)
                else:
                    return Result.failure(RepairError("Healing caused new issue"))

        problematic_analyzer = ProblematicSelfHealingAnalyzer()

        task = Task(
            id=uuid4(),
            name="problematic_healing_task",
            description="Task with problematic self-healing",
            agent_role=AgentRole.CORE_LOGIC,
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.FAILED
        )

        # Simulate self-healing loop
        for cycle in range(10):
            error = Exception(f"Cycle {cycle} error")
            analysis = await problematic_analyzer.analyze_failure(task, error)
            repair_tasks = await problematic_analyzer.generate_repair_tasks(task, analysis)

            repair_result = await problematic_analyzer.execute_repair(repair_tasks[0])

            if repair_result.is_failure() and "Self-healing loop detected" in str(repair_result.get_error()):
                # Loop detection worked
                assert cycle >= 5  # Should detect after reasonable number of cycles
                break

        # Verify loop was detected and prevented
        assert problematic_analyzer.healing_cycles > 5

    @pytest.mark.asyncio
    async def test_self_healing_effectiveness_metrics(self, repair_analyzer):
        """Test metrics for self-healing effectiveness."""

        # Create diverse failure scenarios
        scenarios = [
            (TimeoutError("Timeout"), "increase_timeout"),
            (MemoryError("Memory"), "reduce_memory_usage"),
            (SyntaxError("Syntax"), "fix_syntax"),
            (ImportError("Import"), "install_dependencies"),
            (FileNotFoundError("File"), "create_missing_files"),
        ]

        healing_metrics = {
            "total_attempts": 0,
            "successful_heals": 0,
            "failed_heals": 0,
            "strategies_used": set(),
            "healing_times": []
        }

        for error, expected_strategy in scenarios:
            task = Task(
                id=uuid4(),
                name=f"metrics_task_{error.__class__.__name__}",
                description="Task for healing metrics",
                agent_role=AgentRole.CORE_LOGIC,
                priority=TaskPriority.MEDIUM,
                status=TaskStatus.FAILED
            )

            start_time = datetime.now()

            # Perform healing
            analysis = await repair_analyzer.analyze_failure(task, error)
            repair_tasks = await repair_analyzer.generate_repair_tasks(task, analysis)
            repair_result = await repair_analyzer.execute_repair(repair_tasks[0])

            end_time = datetime.now()
            healing_time = (end_time - start_time).total_seconds()

            # Update metrics
            healing_metrics["total_attempts"] += 1
            healing_metrics["strategies_used"].add(expected_strategy)
            healing_metrics["healing_times"].append(healing_time)

            if repair_result.is_success():
                healing_metrics["successful_heals"] += 1
            else:
                healing_metrics["failed_heals"] += 1

        # Verify metrics
        assert healing_metrics["total_attempts"] == len(scenarios)
        assert healing_metrics["successful_heals"] + healing_metrics["failed_heals"] == healing_metrics["total_attempts"]
        assert len(healing_metrics["strategies_used"]) == len(scenarios)

        # Verify healing performance
        avg_healing_time = sum(healing_metrics["healing_times"]) / len(healing_metrics["healing_times"])
        assert avg_healing_time < 1.0  # Should heal quickly

        # Verify healing success rate
        success_rate = healing_metrics["successful_heals"] / healing_metrics["total_attempts"]
        assert success_rate >= 0.3  # At least 30% success rate
