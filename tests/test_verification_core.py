"""Core verification system tests that work without external dependencies."""

import asyncio
import ast
import py_compile
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

import pytest

# Mock the logger to avoid structlog dependency
mock_logger = MagicMock()
mock_logger.info = MagicMock()
mock_logger.warning = MagicMock()
mock_logger.error = MagicMock()
mock_logger.debug = MagicMock()

# Patch get_logger before imports
with patch('src.utils.app_logging.get_logger', return_value=mock_logger):
    from src.core.interfaces import Artifact, ArtifactType
    from src.verification.verifier_base import (
        VerificationConfig,
        VerificationResult,
        VerificationType,
        VerificationMetrics,
        BaseVerifier,
    )
    from src.verification.compiler_verifiers import (
        PythonVerifier,
        JavaScriptVerifier,
        TypeScriptVerifier,
        get_verifier_for_language,
    )
    from src.verification.repair_analyzer import (
        RepairAnalyzer,
        RepairSuggestion,
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
    async def test_verify_syntax_error(self, verifier):
        """Test detection of syntax errors."""
        artifact = Artifact(
            id=uuid4(),
            type=ArtifactType.SOURCE_CODE,
            name="syntax_error.py",
            content="""
def broken_function(x)  # Missing colon
    return x * 2
""",
            path=Path("syntax_error.py"),
            task_id=uuid4(),
            agent_id=uuid4(),
        )
        
        result = await verifier.verify(artifact)
        
        assert result.success is False
        assert len(result.error_messages) > 0
        assert any("expected ':'" in err or "invalid syntax" in err for err in result.error_messages)
        assert len(result.suggestions) > 0
        assert result.details.get("syntax_error") is not None
    
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


class TestRepairAnalyzer:
    """Test repair analyzer functionality."""
    
    @pytest.fixture
    def analyzer(self):
        """Create a repair analyzer."""
        return RepairAnalyzer()
    
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
        """Test unsupported language returns None."""
        verifier = get_verifier_for_language("cobol")
        assert verifier is None
        
        verifier = get_verifier_for_language("fortran")
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