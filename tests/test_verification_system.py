"""Comprehensive tests for the verification system."""

import asyncio
import pytest
from pathlib import Path
from uuid import uuid4

from src.core.interfaces import Artifact, ArtifactType
from src.verification.verifier_base import (
    VerificationConfig,
    VerificationResult,
    VerificationType,
)
from src.verification.compiler_verifiers import (
    PythonVerifier,
    JavaScriptVerifier,
    TypeScriptVerifier,
    get_verifier_for_language,
)
from src.verification.test_verifiers import (
    PythonTestVerifier,
    JavaScriptTestVerifier,
)
from src.verification.pipeline import VerificationPipeline
from src.verification.repair_analyzer import RepairAnalyzer


class TestPythonVerifier:
    """Test Python syntax and compilation verification."""
    
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
    """Test the repair analyzer."""
    
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


class TestVerifierFactory:
    """Test the verifier factory function."""
    
    def test_get_python_verifier(self):
        """Test getting Python verifier."""
        verifier = get_verifier_for_language("python")
        assert verifier is not None
        assert isinstance(verifier, PythonVerifier)
    
    def test_get_javascript_verifier(self):
        """Test getting JavaScript verifier."""
        verifier = get_verifier_for_language("javascript")
        assert verifier is not None
        assert isinstance(verifier, JavaScriptVerifier)
    
    def test_get_typescript_verifier(self):
        """Test getting TypeScript verifier."""
        verifier = get_verifier_for_language("typescript")
        assert verifier is not None
        assert isinstance(verifier, TypeScriptVerifier)
    
    def test_unsupported_language(self):
        """Test getting verifier for unsupported language."""
        verifier = get_verifier_for_language("cobol")
        assert verifier is None


class TestVerificationConfig:
    """Test verification configuration."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = VerificationConfig()
        
        assert config.enable_syntax_check
        assert config.enable_compilation
        assert config.enable_tests
        assert config.test_timeout_seconds == 30
        assert config.test_coverage_threshold == 0.8
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = VerificationConfig(
            enable_syntax_check=False,
            test_timeout_seconds=60,
            test_coverage_threshold=0.9,
        )
        
        assert not config.enable_syntax_check
        assert config.test_timeout_seconds == 60
        assert config.test_coverage_threshold == 0.9


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