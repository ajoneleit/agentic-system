"""Comprehensive verification system tests.

Consolidates all verification system tests including core functionality,
external dependencies, and integration testing.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

# Mock the logger to avoid structlog dependency in core tests
mock_logger = MagicMock()
mock_logger.info = MagicMock()
mock_logger.warning = MagicMock()
mock_logger.error = MagicMock()
mock_logger.debug = MagicMock()

# Patch get_logger before imports
with patch('src.utils.app_logging.get_logger', return_value=mock_logger):
    from src.core.interfaces import Artifact, ArtifactType
    from src.verification.compiler_verifiers import (
        JavaScriptVerifier,
        PythonVerifier,
        TypeScriptVerifier,
        get_verifier_for_language,
    )
    from src.verification.pipeline import VerificationPipeline
    from src.verification.repair_analyzer import (
        RepairAnalyzer,
    )
    from src.verification.test_verifiers import (
        PythonTestVerifier,
    )
    from src.verification.verifier_base import (
        BaseVerifier,
        VerificationConfig,
        VerificationResult,
        VerificationType,
    )


class TestVerificationResult:
    """Test VerificationResult functionality."""

    def test_create_result(self):
        """Test creating a verification result."""
        result = VerificationResult(
            success=True,
            verification_type=VerificationType.COMPILATION,
            artifact_id=uuid4(),
            verifier_name="TestVerifier",
        )

        assert result.success is True
        assert result.verification_type == VerificationType.COMPILATION
        assert result.verifier_name == "TestVerifier"
        assert len(result.error_messages) == 0

    def test_add_messages(self):
        """Test adding different message types."""
        result = VerificationResult(
            success=True,
            verification_type=VerificationType.SYNTAX,
            artifact_id=uuid4(),
            verifier_name="TestVerifier",
        )

        # Add info
        result.add_info("Test info")
        assert len(result.info_messages) == 1
        assert result.info_messages[0] == "Test info"
        assert result.success is True

        # Add warning
        result.add_warning("Test warning")
        assert len(result.warnings) == 1
        assert result.warnings[0] == "Test warning"
        assert result.success is True

        # Add error - should change success to False
        result.add_error("Test error")
        assert len(result.error_messages) == 1
        assert result.error_messages[0] == "Test error"
        assert result.success is False

    def test_completion(self):
        """Test result completion."""
        result = VerificationResult(
            success=True,
            verification_type=VerificationType.TEST,
            artifact_id=uuid4(),
            verifier_name="TestVerifier",
        )

        # Complete the result
        result.complete()

        assert result.completed_at is not None
        assert result.metrics.execution_time >= 0


class TestVerificationConfig:
    """Test VerificationConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = VerificationConfig()

        assert config.enable_syntax_check is True
        assert config.enable_compilation is True
        assert config.enable_tests is True
        assert config.test_timeout_seconds == 30
        assert config.test_coverage_threshold == 0.8
        assert config.max_parallel_verifications == 4

    def test_custom_config(self):
        """Test custom configuration."""
        config = VerificationConfig(
            enable_syntax_check=False,
            enable_compilation=True,
            enable_tests=False,
            test_timeout_seconds=60,
            test_coverage_threshold=0.9,
            max_parallel_verifications=8,
        )

        assert config.enable_syntax_check is False
        assert config.enable_compilation is True
        assert config.enable_tests is False
        assert config.test_timeout_seconds == 60
        assert config.test_coverage_threshold == 0.9
        assert config.max_parallel_verifications == 8


class TestPythonVerifier:
    """Test Python verifier functionality."""

    @pytest.fixture
    def verifier(self):
        """Create a Python verifier."""
        return PythonVerifier()

    @pytest.fixture
    def valid_python_artifact(self):
        """Create an artifact with valid Python code."""
        return Artifact(
            id=uuid4(),
            type=ArtifactType.SOURCE_CODE,
            name="valid_code.py",
            content="""
def greet(name):
    '''Greet a person by name.'''
    return f"Hello, {name}!"

def main():
    print(greet("World"))

if __name__ == "__main__":
    main()
""",
            path=Path("valid_code.py"),
            task_id=uuid4(),
            agent_id=uuid4(),
        )

    @pytest.fixture
    def syntax_error_artifact(self):
        """Create an artifact with syntax error."""
        return Artifact(
            id=uuid4(),
            type=ArtifactType.SOURCE_CODE,
            name="syntax_error.py",
            content="""
def greet(name)  # Missing colon
    return f"Hello, {name}!"
""",
            path=Path("syntax_error.py"),
            task_id=uuid4(),
            agent_id=uuid4(),
        )

    @pytest.mark.asyncio
    async def test_verify_valid_code(self, verifier):
        """Test verification of valid Python code."""
        artifact = Artifact(
            id=uuid4(),
            type=ArtifactType.SOURCE_CODE,
            name="valid.py",
            content="""
def add(a, b):
    '''Add two numbers.'''
    return a + b

def multiply(a, b):
    '''Multiply two numbers.'''
    return a * b

result = add(2, 3)
print(f"Result: {result}")
""",
            path=Path("valid.py"),
            task_id=uuid4(),
            agent_id=uuid4(),
        )

        result = await verifier.verify(artifact)

        assert result.success is True
        assert len(result.error_messages) == 0
        assert result.metrics.lines_of_code == 11
        assert result.details.get("ast_stats", {}).get("functions") == 2

    @pytest.mark.asyncio
    async def test_valid_python_code(self, verifier, valid_python_artifact):
        """Test verification of valid Python code."""
        result = await verifier.verify(valid_python_artifact)

        assert result.success
        assert len(result.error_messages) == 0
        assert result.verification_type == VerificationType.COMPILATION
        assert result.metrics.lines_of_code > 0

    @pytest.mark.asyncio
    async def test_syntax_error_detection(self, verifier, syntax_error_artifact):
        """Test detection of syntax errors."""
        result = await verifier.verify(syntax_error_artifact)

        assert not result.success
        assert len(result.error_messages) > 0
        assert any("expected ':'" in err for err in result.error_messages)
        assert len(result.suggestions) > 0

    @pytest.mark.asyncio
    async def test_verify_indentation_error(self, verifier):
        """Test detection of indentation errors."""
        artifact = Artifact(
            id=uuid4(),
            type=ArtifactType.SOURCE_CODE,
            name="indent_error.py",
            content="""
def my_function():
return "bad indent"
""",
            path=Path("indent_error.py"),
            task_id=uuid4(),
            agent_id=uuid4(),
        )

        result = await verifier.verify(artifact)

        assert result.success is False
        assert any("indent" in err.lower() for err in result.error_messages)

    @pytest.mark.asyncio
    async def test_verify_empty_content(self, verifier):
        """Test handling of empty content."""
        artifact = Artifact(
            id=uuid4(),
            type=ArtifactType.SOURCE_CODE,
            name="empty.py",
            content="",
            path=Path("empty.py"),
            task_id=uuid4(),
            agent_id=uuid4(),
        )

        result = await verifier.verify(artifact)

        assert result.success is False
        assert any("No code content" in err for err in result.error_messages)

    @pytest.mark.asyncio
    async def test_import_warning(self, verifier):
        """Test import checking."""
        artifact = Artifact(
            id=uuid4(),
            type=ArtifactType.SOURCE_CODE,
            name="import_test.py",
            content="import os\nimport sys\nprint('hello')",
            path=Path("import_test.py"),
            task_id=uuid4(),
            agent_id=uuid4(),
        )

        result = await verifier.verify(artifact)
        assert result.success  # Standard library imports should pass

    @pytest.mark.asyncio
    async def test_can_verify(self, verifier):
        """Test can_verify method."""
        # Should verify Python source code
        py_artifact = Artifact(
            id=uuid4(),
            type=ArtifactType.SOURCE_CODE,
            name="test.py",
            content="print('hello')",
            path=Path("test.py"),
            task_id=uuid4(),
            agent_id=uuid4(),
        )
        assert await verifier.can_verify(py_artifact) is True

        # Should not verify JavaScript
        js_artifact = Artifact(
            id=uuid4(),
            type=ArtifactType.SOURCE_CODE,
            name="test.js",
            content="console.log('hello')",
            path=Path("test.js"),
            task_id=uuid4(),
            agent_id=uuid4(),
        )
        assert await verifier.can_verify(js_artifact) is False


class TestJavaScriptVerifier:
    """Test JavaScript syntax verification."""

    @pytest.fixture
    def verifier(self):
        """Create a JavaScript verifier."""
        return JavaScriptVerifier()

    @pytest.fixture
    def valid_js_artifact(self):
        """Create an artifact with valid JavaScript code."""
        return Artifact(
            id=uuid4(),
            type=ArtifactType.SOURCE_CODE,
            name="valid_code.js",
            content="""
function greet(name) {
    return `Hello, ${name}!`;
}

const main = () => {
    console.log(greet("World"));
};

main();
""",
            path=Path("valid_code.js"),
            task_id=uuid4(),
            agent_id=uuid4(),
        )

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not asyncio.run(JavaScriptVerifier()._check_node_available()),
        reason="Node.js not available"
    )
    async def test_valid_javascript_code(self, verifier, valid_js_artifact):
        """Test verification of valid JavaScript code."""
        result = await verifier.verify(valid_js_artifact)

        assert result.success
        assert len(result.error_messages) == 0
        assert result.verification_type == VerificationType.SYNTAX


class TestPythonTestVerifier:
    """Test Python test execution verification."""

    @pytest.fixture
    def verifier(self):
        """Create a Python test verifier."""
        return PythonTestVerifier()

    @pytest.fixture
    def test_artifact(self):
        """Create a test artifact."""
        return Artifact(
            id=uuid4(),
            type=ArtifactType.TEST_CODE,
            name="test_example.py",
            content="""
def test_addition():
    assert 1 + 1 == 2

def test_subtraction():
    assert 5 - 3 == 2

def test_multiplication():
    assert 3 * 4 == 12
""",
            path=Path("test_example.py"),
            task_id=uuid4(),
            agent_id=uuid4(),
        )

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not asyncio.run(PythonTestVerifier()._check_pytest_available()),
        reason="pytest not available"
    )
    async def test_passing_tests(self, verifier, test_artifact):
        """Test execution of passing tests."""
        result = await verifier.verify(test_artifact)

        assert result.success
        assert result.metrics.tests_total == 3
        assert result.metrics.tests_passed == 3
        assert result.metrics.tests_failed == 0


class TestVerificationPipeline:
    """Test the verification pipeline orchestrator."""

    @pytest.fixture
    def pipeline(self):
        """Create a verification pipeline."""
        config = VerificationConfig(
            enable_syntax_check=True,
            enable_compilation=True,
            enable_tests=True,
        )
        return VerificationPipeline(config)

    @pytest.fixture
    def mixed_artifacts(self):
        """Create a mix of artifacts."""
        return [
            Artifact(
                id=uuid4(),
                type=ArtifactType.SOURCE_CODE,
                name="calculator.py",
                content="""
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
""",
                path=Path("calculator.py"),
                task_id=uuid4(),
                agent_id=uuid4(),
            ),
            Artifact(
                id=uuid4(),
                type=ArtifactType.TEST_CODE,
                name="test_calculator.py",
                content="""
from calculator import add, subtract

def test_add():
    assert add(2, 3) == 5

def test_subtract():
    assert subtract(5, 3) == 2
""",
                path=Path("test_calculator.py"),
                task_id=uuid4(),
                agent_id=uuid4(),
            ),
        ]

    @pytest.mark.asyncio
    async def test_pipeline_execution(self, pipeline, mixed_artifacts):
        """Test running the full pipeline."""
        result = await pipeline.verify_artifacts(mixed_artifacts)

        assert result.total_artifacts == 2
        assert result.syntax_checks > 0 or result.compilation_checks > 0
        # Note: Test execution may fail due to import issues in isolated test


class TestRepairAnalyzer:
    """Test repair analyzer functionality."""

    @pytest.fixture
    def analyzer(self):
        """Create a repair analyzer."""
        return RepairAnalyzer()

    @pytest.fixture
    def syntax_error_result(self):
        """Create a verification result with syntax error."""
        result = VerificationResult(
            success=False,
            verification_type=VerificationType.SYNTAX,
            artifact_id=uuid4(),
            verifier_name="PythonVerifier",
        )
        result.add_error("SyntaxError: expected ':' at line 2")
        result.details["syntax_error"] = {
            "line": 2,
            "column": 15,
            "message": "expected ':'",
        }
        return result

    @pytest.mark.asyncio
    async def test_analyze_syntax_error_missing_colon(self, analyzer):
        """Test analysis of missing colon error."""
        # Create verification result with error
        verification_result = VerificationResult(
            success=False,
            verification_type=VerificationType.SYNTAX,
            artifact_id=uuid4(),
            verifier_name="PythonVerifier",
        )
        verification_result.add_error("SyntaxError: expected ':' at line 2")
        verification_result.details["syntax_error"] = {
            "line": 2,
            "column": 20,
            "message": "expected ':'",
        }

        # Create artifact
        artifact = Artifact(
            id=verification_result.artifact_id,
            type=ArtifactType.SOURCE_CODE,
            name="missing_colon.py",
            content="def my_function(x)\n    return x * 2",
            path=Path("missing_colon.py"),
            task_id=uuid4(),
            agent_id=uuid4(),
        )

        suggestion = await analyzer.analyze_syntax_error(artifact, verification_result)

        assert suggestion is not None
        assert suggestion.failure_type == "syntax"
        assert suggestion.severity == "critical"
        assert "colon" in suggestion.suggestion.lower()
        assert "missing colon" in suggestion.repair_prompt.lower()

    @pytest.mark.asyncio
    async def test_syntax_error_analysis(self, analyzer, syntax_error_result):
        """Test analysis of syntax errors."""
        artifact = Artifact(
            id=syntax_error_result.artifact_id,
            type=ArtifactType.SOURCE_CODE,
            name="error_code.py",
            content="def greet(name)\n    return f'Hello, {name}!'",
            path=Path("error_code.py"),
            task_id=uuid4(),
            agent_id=uuid4(),
        )

        suggestion = await analyzer.analyze_syntax_error(artifact, syntax_error_result)

        assert suggestion is not None
        assert suggestion.failure_type == "syntax"
        assert suggestion.severity == "critical"
        assert "colon" in suggestion.suggestion.lower()
        assert len(suggestion.repair_prompt) > 0

    @pytest.mark.asyncio
    async def test_analyze_indentation_error(self, analyzer):
        """Test analysis of indentation error."""
        verification_result = VerificationResult(
            success=False,
            verification_type=VerificationType.SYNTAX,
            artifact_id=uuid4(),
            verifier_name="PythonVerifier",
        )
        verification_result.add_error("IndentationError: expected an indented block")

        artifact = Artifact(
            id=verification_result.artifact_id,
            type=ArtifactType.SOURCE_CODE,
            name="indent_error.py",
            content="def func():\nprint('bad')",
            path=Path("indent_error.py"),
            task_id=uuid4(),
            agent_id=uuid4(),
        )

        suggestion = await analyzer.analyze_syntax_error(artifact, verification_result)

        assert suggestion is not None
        assert "indent" in suggestion.suggestion.lower()
        assert "indentation" in suggestion.repair_prompt.lower()

    @pytest.mark.asyncio
    async def test_analyze_no_errors(self, analyzer):
        """Test analysis when no errors present."""
        verification_result = VerificationResult(
            success=True,
            verification_type=VerificationType.SYNTAX,
            artifact_id=uuid4(),
            verifier_name="PythonVerifier",
        )

        artifact = Artifact(
            id=verification_result.artifact_id,
            type=ArtifactType.SOURCE_CODE,
            name="good.py",
            content="print('hello')",
            path=Path("good.py"),
            task_id=uuid4(),
            agent_id=uuid4(),
        )

        suggestion = await analyzer.analyze_syntax_error(artifact, verification_result)

        assert suggestion is None


class TestVerifierFactory:
    """Test verifier factory function."""

    def test_get_python_verifier(self):
        """Test getting Python verifier."""
        verifier = get_verifier_for_language("python")
        assert verifier is not None
        assert isinstance(verifier, PythonVerifier)
        assert verifier.name == "PythonVerifier"

    def test_get_javascript_verifier(self):
        """Test getting JavaScript verifier."""
        verifier = get_verifier_for_language("javascript")
        assert verifier is not None
        assert isinstance(verifier, JavaScriptVerifier)
        assert verifier.name == "JavaScriptVerifier"

    def test_get_typescript_verifier(self):
        """Test getting TypeScript verifier."""
        verifier = get_verifier_for_language("typescript")
        assert verifier is not None
        assert isinstance(verifier, TypeScriptVerifier)
        assert verifier.name == "TypeScriptVerifier"

    def test_case_insensitive(self):
        """Test case insensitive language names."""
        verifier1 = get_verifier_for_language("Python")
        verifier2 = get_verifier_for_language("PYTHON")
        verifier3 = get_verifier_for_language("python")

        assert all(v is not None for v in [verifier1, verifier2, verifier3])
        assert all(isinstance(v, PythonVerifier) for v in [verifier1, verifier2, verifier3])

    def test_unsupported_language(self):
        """Test getting verifier for unsupported language."""
        verifier = get_verifier_for_language("cobol")
        assert verifier is None


class TestBaseVerifierLanguageDetection:
    """Test language detection functionality."""

    def test_detect_language_by_extension(self):
        """Test language detection from file extensions."""
        # Create a mock verifier to test protected method
        class TestVerifier(BaseVerifier):
            @property
            def name(self): return "TestVerifier"

            @property
            def verification_type(self): return VerificationType.SYNTAX

            async def verify(self, artifact, context=None):
                return self._create_result(artifact)

        verifier = TestVerifier()

        # Test various extensions
        test_cases = [
            ("test.py", "python"),
            ("test.js", "javascript"),
            ("test.ts", "typescript"),
            ("test.java", "java"),
            ("test.go", "go"),
            ("test.rs", "rust"),
            ("test.cpp", "cpp"),
            ("test.c", "c"),
            ("test.rb", "ruby"),
            ("test.php", "php"),
        ]

        for filename, expected_lang in test_cases:
            artifact = Artifact(
                id=uuid4(),
                type=ArtifactType.SOURCE_CODE,
                name=filename,
                content="",
                path=Path(filename),
                task_id=uuid4(),
                agent_id=uuid4(),
            )
            detected = verifier._detect_language(artifact)
            assert detected == expected_lang, f"Expected {expected_lang} for {filename}, got {detected}"


@pytest.mark.integration
class TestVerificationIntegration:
    """Integration tests for the verification system."""

    @pytest.mark.asyncio
    async def test_full_verification_flow(self):
        """Test the complete verification flow."""
        # Create artifacts
        source_artifact = Artifact(
            id=uuid4(),
            type=ArtifactType.SOURCE_CODE,
            name="example.py",
            content="""
def factorial(n):
    if n < 0:
        raise ValueError("Negative numbers not allowed")
    elif n == 0:
        return 1
    else:
        return n * factorial(n - 1)
""",
            path=Path("example.py"),
            task_id=uuid4(),
            agent_id=uuid4(),
        )

        test_artifact = Artifact(
            id=uuid4(),
            type=ArtifactType.TEST_CODE,
            name="test_example.py",
            content="""
def test_factorial_zero():
    from example import factorial
    assert factorial(0) == 1

def test_factorial_positive():
    from example import factorial
    assert factorial(5) == 120

def test_factorial_negative():
    from example import factorial
    import pytest
    with pytest.raises(ValueError):
        factorial(-1)
""",
            path=Path("test_example.py"),
            task_id=uuid4(),
            agent_id=uuid4(),
        )

        # Create pipeline
        pipeline = VerificationPipeline()

        # Run verification
        result = await pipeline.verify_artifacts([source_artifact, test_artifact])

        # Check results
        assert result.total_artifacts == 2
        assert result.compilation_checks >= 1  # At least source code compiled
        # Test execution may fail due to import issues in isolated environment


if __name__ == "__main__":
    # Run tests with pytest if available, otherwise run a simple test
    try:
        import pytest
        sys.exit(pytest.main([__file__, "-v"]))
    except ImportError:
        print("pytest not available, running basic test")
        # Run a simple async test
        async def basic_test():
            verifier = PythonVerifier()
            artifact = Artifact(
                id=uuid4(),
                type=ArtifactType.SOURCE_CODE,
                name="test.py",
                content="print('Hello, World!')",
                path=Path("test.py"),
                task_id=uuid4(),
                agent_id=uuid4(),
            )
            result = await verifier.verify(artifact)
            print(f"Verification success: {result.success}")
            print(f"Lines of code: {result.metrics.lines_of_code}")
            return result.success

        import asyncio
        success = asyncio.run(basic_test())
        sys.exit(0 if success else 1)
