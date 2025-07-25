"""
Verification system for autonomous coding system.

This module provides comprehensive verification capabilities including:
- Compiler verification (syntax and type checking)
- Test verification (pytest, jest, mocha)
- Sequential verification pipeline
- Database integration and persistence
- High-level verification service

The system supports Python, JavaScript, and TypeScript with extensible
architecture for additional languages.
"""

from .interfaces import (
    VerificationContext,
    VerificationResult,
    VerificationSummary,
    VerifierInterface,
    CompilerVerifierInterface,
    TestVerifierInterface,
    VerificationPipelineInterface,
    VerificationServiceInterface
)

from .models import (
    LanguageType,
    VerificationStage,
    VerificationStatus,
    VerificationResult as DBVerificationResult,
    VerificationSession,
    VerificationTemplate,
    VerificationMetrics
)

from .verifiers.compiler_verifier import CompilerVerifier
from .verifiers.test_verifier import TestVerifier
from .verifiers.python_verifier import PythonCompilerVerifier
from .verifiers.javascript_verifier import JavaScriptCompilerVerifier
from .verifiers.python_test_verifier import PythonTestVerifier
from .verifiers.javascript_test_verifier import JavaScriptTestVerifier

from .pipeline import VerificationPipeline
from .service import VerificationService

__all__ = [
    # Interfaces
    "VerificationContext",
    "VerificationResult", 
    "VerificationSummary",
    "VerifierInterface",
    "CompilerVerifierInterface",
    "TestVerifierInterface", 
    "VerificationPipelineInterface",
    "VerificationServiceInterface",
    
    # Models
    "LanguageType",
    "VerificationStage",
    "VerificationStatus",
    "DBVerificationResult",
    "VerificationSession",
    "VerificationTemplate",
    "VerificationMetrics",
    
    # Verifiers
    "CompilerVerifier",
    "TestVerifier",
    "PythonCompilerVerifier",
    "JavaScriptCompilerVerifier",
    "PythonTestVerifier",
    "JavaScriptTestVerifier",
    
    # Pipeline and Service
    "VerificationPipeline",
    "VerificationService"
]

# Version information
__version__ = "1.0.0"
__author__ = "Agentic System"
__description__ = "Comprehensive verification system for autonomous coding"