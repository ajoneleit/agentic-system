"""Example agent implementation using Result[T] pattern.

This module demonstrates how to implement agents using the Result[T] monad
for robust error handling instead of exceptions.
"""

import asyncio
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4

from src.agents.sub_agent import BaseSubAgent
from src.core.interfaces import (
    Task,
    TaskContext,
    Artifact,
    ArtifactType,
    AgentRole,
)
from src.core.result import Result, collect_results, async_result_handler
from src.core.result_integration import (
    ResultChain,
    AsyncResultChain,
    execute_parallel_with_results,
    log_result_errors,
    retry_with_result,
    validate_result,
)
from src.core.task_result import TaskResult
from src.utils.app_logging import get_logger

logger = get_logger(__name__)


class ResultBasedCodeAgent(BaseSubAgent):
    """Example code generation agent using Result[T] pattern."""
    
    def __init__(self):
        """Initialize the Result-based code agent."""
        super().__init__(AgentRole.CODE_GENERATOR)
    
    async def _execute_task_impl(
        self,
        task: Task,
        context: TaskContext
    ) -> List[Artifact]:
        """Execute task implementation with Result[T] pattern.
        
        This method overrides the base implementation to use Result[T]
        for all operations instead of raising exceptions.
        """
        # Convert the entire task execution to Result-based flow
        result = await (
            AsyncResultChain(self._validate_task_input(task))
            .then(lambda _: self._generate_code_from_prompt(task, context))
            .then(lambda code: self._validate_generated_code(code))
            .then(lambda code: self._create_artifacts(code, task))
            .get()
        )
        
        # Log any errors and unwrap the result
        result = log_result_errors("ResultBasedCodeAgent", "task_execution")(result)
        
        # Handle the result
        return result.unwrap_or_else(
            lambda e: self._handle_generation_error(e, task)
        )
    
    async def _validate_task_input(self, task: Task) -> Result[None]:
        """Validate task input parameters.
        
        Returns:
            Result.success(None) if valid, Result.failure otherwise
        """
        if not task.description:
            return Result.failure(
                ValueError("Task description cannot be empty")
            )
        
        if not task.metadata.get("language"):
            return Result.failure(
                ValueError("Programming language not specified in task metadata")
            )
        
        return Result.success(None)
    
    async def _generate_code_from_prompt(
        self,
        task: Task,
        context: TaskContext
    ) -> Result[str]:
        """Generate code using LLM with Result return type.
        
        Returns:
            Result[str] containing generated code or error
        """
        # Simulate async operation with potential failure
        await asyncio.sleep(0.1)
        
        # Use retry for resilience
        async def generate_with_llm() -> Result[str]:
            try:
                # This would be the actual LLM call
                prompt = self._build_generation_prompt(task)
                
                # Simulate response
                if "error" in task.description.lower():
                    return Result.failure(
                        RuntimeError("Simulated LLM generation failure")
                    )
                
                code = f"""
# Generated code for: {task.description}
def hello_world():
    print("Hello, World!")
    
if __name__ == "__main__":
    hello_world()
"""
                return Result.success(code)
            except Exception as e:
                return Result.failure(e)
        
        # Retry up to 3 times with exponential backoff
        return await retry_with_result(
            generate_with_llm,
            max_attempts=3,
            delay=1.0,
            backoff_factor=2.0
        )
    
    def _validate_generated_code(self, code: str) -> Result[str]:
        """Validate generated code syntax and structure.
        
        Returns:
            Result[str] with validated code or error
        """
        if not code.strip():
            return Result.failure(
                ValueError("Generated code is empty")
            )
        
        # Basic syntax validation (in real implementation, use AST)
        try:
            compile(code, "<string>", "exec")
            return Result.success(code)
        except SyntaxError as e:
            return Result.failure(
                SyntaxError(f"Generated code has syntax errors: {e}")
            )
    
    async def _create_artifacts(
        self,
        code: str,
        task: Task
    ) -> Result[List[Artifact]]:
        """Create artifacts from generated code.
        
        Returns:
            Result[List[Artifact]] with created artifacts or error
        """
        language = task.metadata.get("language", "python")
        extension = self._get_file_extension(language)
        
        artifact = Artifact(
            id=uuid4(),
            name=f"generated_code{extension}",
            type=ArtifactType.CODE,
            content=code,
            metadata={
                "language": language,
                "task_id": str(task.id),
                "generated_by": str(self.id),
            }
        )
        
        return Result.success([artifact])
    
    def _get_file_extension(self, language: str) -> str:
        """Get file extension for language."""
        extensions = {
            "python": ".py",
            "javascript": ".js",
            "typescript": ".ts",
            "java": ".java",
            "cpp": ".cpp",
            "go": ".go",
        }
        return extensions.get(language.lower(), ".txt")
    
    def _build_generation_prompt(self, task: Task) -> str:
        """Build prompt for code generation."""
        return f"""
Generate {task.metadata.get('language', 'Python')} code for the following task:

{task.description}

Requirements:
- Include proper error handling
- Add helpful comments
- Follow best practices
"""
    
    def _handle_generation_error(
        self,
        error: Exception,
        task: Task
    ) -> List[Artifact]:
        """Handle generation errors by creating error artifact."""
        logger.error(
            "Code generation failed",
            task_id=str(task.id),
            error=str(error)
        )
        
        # Create error artifact for debugging
        error_artifact = Artifact(
            id=uuid4(),
            name="generation_error.txt",
            type=ArtifactType.CODE,
            content=f"""
# Code Generation Failed

Task: {task.description}
Error: {str(error)}

This is a placeholder artifact created due to generation failure.
Please review the error and retry the task.
""",
            metadata={
                "error": True,
                "error_type": type(error).__name__,
                "task_id": str(task.id),
            }
        )
        
        return [error_artifact]


class ResultBasedTestAgent(BaseSubAgent):
    """Example test generation agent using Result[T] pattern."""
    
    def __init__(self):
        """Initialize the Result-based test agent."""
        super().__init__(AgentRole.TEST_WRITER)
    
    async def _execute_task_impl(
        self,
        task: Task,
        context: TaskContext
    ) -> List[Artifact]:
        """Execute test generation with Result[T] pattern."""
        # Parallel operations example
        operations = [
            lambda: self._analyze_code_to_test(task, context),
            lambda: self._determine_test_strategy(task),
            lambda: self._load_test_templates(task),
        ]
        
        # Execute analysis operations in parallel
        analysis_result = await execute_parallel_with_results(operations)
        
        if analysis_result.is_failure():
            logger.error("Test analysis failed", error=str(analysis_result.get_error()))
            return []
        
        code_analysis, test_strategy, templates = analysis_result.unwrap()
        
        # Generate tests based on analysis
        test_result = await self._generate_tests(
            code_analysis,
            test_strategy,
            templates,
            task
        )
        
        return test_result.unwrap_or_else(
            lambda e: self._create_fallback_tests(e, task)
        )
    
    async def _analyze_code_to_test(
        self,
        task: Task,
        context: TaskContext
    ) -> Result[Dict[str, Any]]:
        """Analyze code artifact to test."""
        code_artifact_id = task.metadata.get("code_artifact_id")
        if not code_artifact_id:
            return Result.failure(
                ValueError("No code artifact ID provided")
            )
        
        # Simulate analysis
        await asyncio.sleep(0.1)
        
        return Result.success({
            "functions": ["hello_world"],
            "classes": [],
            "complexity": "low",
            "test_points": ["function output", "edge cases"],
        })
    
    async def _determine_test_strategy(
        self,
        task: Task
    ) -> Result[str]:
        """Determine testing strategy."""
        # Simulate strategy determination
        await asyncio.sleep(0.05)
        
        if "unit" in task.description.lower():
            return Result.success("unit")
        elif "integration" in task.description.lower():
            return Result.success("integration")
        else:
            return Result.success("mixed")
    
    async def _load_test_templates(
        self,
        task: Task
    ) -> Result[Dict[str, str]]:
        """Load test templates for the language."""
        language = task.metadata.get("language", "python")
        
        # Simulate template loading
        await asyncio.sleep(0.05)
        
        templates = {
            "python": """
import unittest
from {module} import {function}

class Test{Function}(unittest.TestCase):
    def test_{test_name}(self):
        {test_body}

if __name__ == '__main__':
    unittest.main()
""",
            "javascript": """
const {{ {function} }} = require('./{module}');

describe('{function}', () => {{
    test('{test_name}', () => {{
        {test_body}
    }});
}});
"""
        }
        
        template = templates.get(language)
        if not template:
            return Result.failure(
                ValueError(f"No test template for language: {language}")
            )
        
        return Result.success({"template": template})
    
    async def _generate_tests(
        self,
        code_analysis: Dict[str, Any],
        test_strategy: str,
        templates: Dict[str, str],
        task: Task
    ) -> Result[List[Artifact]]:
        """Generate test artifacts."""
        # Generate tests based on analysis
        test_content = templates["template"].format(
            module="generated_code",
            function="hello_world",
            Function="HelloWorld",
            test_name="output",
            test_body="self.assertEqual(hello_world(), None)"
        )
        
        artifact = Artifact(
            id=uuid4(),
            name="test_generated_code.py",
            type=ArtifactType.TEST,
            content=test_content,
            metadata={
                "test_strategy": test_strategy,
                "code_analysis": code_analysis,
                "task_id": str(task.id),
            }
        )
        
        return Result.success([artifact])
    
    def _create_fallback_tests(
        self,
        error: Exception,
        task: Task
    ) -> List[Artifact]:
        """Create basic fallback tests on error."""
        logger.warning(
            "Creating fallback tests due to generation error",
            error=str(error)
        )
        
        fallback_content = """
# Fallback test file
# Test generation failed - please implement tests manually

def test_placeholder():
    \"\"\"Placeholder test - implement actual tests here.\"\"\"
    assert True  # Replace with actual test
"""
        
        artifact = Artifact(
            id=uuid4(),
            name="test_fallback.py",
            type=ArtifactType.TEST,
            content=fallback_content,
            metadata={
                "fallback": True,
                "error": str(error),
                "task_id": str(task.id),
            }
        )
        
        return [artifact]


# Example of Result-based task execution
async def execute_task_with_result(
    agent: BaseSubAgent,
    task: Task,
    context: TaskContext
) -> Result[TaskResult]:
    """Execute a task and return Result[TaskResult].
    
    This demonstrates how task execution can be wrapped in Result[T]
    for better error handling at the orchestration level.
    """
    try:
        # Validate agent is initialized
        if not agent._is_initialized:
            return Result.failure(
                RuntimeError(f"Agent {agent.id} not initialized")
            )
        
        # Execute the task
        task_result = await agent.execute_task(task, context)
        
        # Validate result
        if not task_result.success:
            return Result.failure(
                RuntimeError(f"Task execution failed: {task_result.error}")
            )
        
        return Result.success(task_result)
        
    except Exception as e:
        logger.error(
            "Unexpected error in task execution",
            agent_id=str(agent.id),
            task_id=str(task.id),
            error=str(e)
        )
        return Result.failure(e)