"""
Verification pipeline implementation.

This module provides a sequential verification pipeline that orchestrates
compiler verification followed by test verification with comprehensive
error handling and result aggregation.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.verification.interfaces import (
    VerificationContext,
    VerificationResult,
    VerificationSummary,
    VerificationPipelineInterface
)
from src.verification.models import LanguageType, VerificationStage, VerificationStatus
from src.verification.verifiers.compiler_verifier import CompilerVerifier
from src.verification.verifiers.test_verifier import TestVerifier
from src.verification.verifiers.python_verifier import PythonCompilerVerifier
from src.verification.verifiers.javascript_verifier import JavaScriptCompilerVerifier
from src.verification.verifiers.python_test_verifier import PythonTestVerifier
from src.verification.verifiers.javascript_test_verifier import JavaScriptTestVerifier

logger = logging.getLogger(__name__)


class VerificationPipeline(VerificationPipelineInterface):
    """Sequential verification pipeline implementing compile → test workflow."""
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the verification pipeline.
        
        Args:
            config: Configuration dictionary for the pipeline
        """
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Pipeline configuration
        self.stop_on_compiler_failure = self.config.get("stop_on_compiler_failure", True)
        self.parallel_execution = self.config.get("parallel_execution", False)
        self.timeout = self.config.get("timeout", 600)  # 10 minutes total
        self.enable_compiler_verification = self.config.get("enable_compiler_verification", True)
        self.enable_test_verification = self.config.get("enable_test_verification", True)
        
        # Initialize verifier registries
        self._compiler_verifiers: Dict[LanguageType, CompilerVerifier] = {}
        self._test_verifiers: Dict[LanguageType, TestVerifier] = {}
        
        # Register default verifiers
        self._register_default_verifiers()
    
    def _register_default_verifiers(self):
        """Register default verifiers for supported languages."""
        try:
            # Register compiler verifiers
            python_compiler_config = self.config.get("python_compiler", {})
            self._compiler_verifiers[LanguageType.PYTHON] = PythonCompilerVerifier(python_compiler_config)
            
            javascript_compiler_config = self.config.get("javascript_compiler", {})
            js_verifier = JavaScriptCompilerVerifier(javascript_compiler_config)
            self._compiler_verifiers[LanguageType.JAVASCRIPT] = js_verifier
            self._compiler_verifiers[LanguageType.TYPESCRIPT] = js_verifier
            
            # Register test verifiers
            python_test_config = self.config.get("python_test", {})
            self._test_verifiers[LanguageType.PYTHON] = PythonTestVerifier(python_test_config)
            
            javascript_test_config = self.config.get("javascript_test", {})
            js_test_verifier = JavaScriptTestVerifier(javascript_test_config)
            self._test_verifiers[LanguageType.JAVASCRIPT] = js_test_verifier
            self._test_verifiers[LanguageType.TYPESCRIPT] = js_test_verifier
            
            self.logger.info("Default verifiers registered successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to register default verifiers: {str(e)}")
    
    def register_compiler_verifier(self, language: LanguageType, verifier: CompilerVerifier):
        """Register a compiler verifier for a specific language.
        
        Args:
            language: Language type
            verifier: Compiler verifier instance
        """
        self._compiler_verifiers[language] = verifier
        self.logger.info(f"Registered compiler verifier for {language.value}")
    
    def register_test_verifier(self, language: LanguageType, verifier: TestVerifier):
        """Register a test verifier for a specific language.
        
        Args:
            language: Language type
            verifier: Test verifier instance
        """
        self._test_verifiers[language] = verifier
        self.logger.info(f"Registered test verifier for {language.value}")
    
    async def verify(self, context: VerificationContext) -> VerificationSummary:
        """
        Execute the complete verification pipeline.
        
        Args:
            context: Verification context
            
        Returns:
            VerificationSummary with results from all stages
        """
        started_at = datetime.utcnow()
        
        try:
            self.logger.info(f"Starting verification pipeline for {context.language.value}")
            
            # Initialize results tracking
            results: List[VerificationResult] = []
            overall_success = True
            
            # Stage 1: Compiler Verification
            if self.enable_compiler_verification:
                compiler_result = await self._run_compiler_verification(context)
                results.append(compiler_result)
                
                if not compiler_result.success:
                    overall_success = False
                    if self.stop_on_compiler_failure:
                        self.logger.warning("Compiler verification failed, skipping test verification")
                        return self._create_summary(results, started_at, overall_success)
            
            # Stage 2: Test Verification
            if self.enable_test_verification:
                test_result = await self._run_test_verification(context)
                results.append(test_result)
                
                if not test_result.success:
                    overall_success = False
            
            completed_at = datetime.utcnow()
            self.logger.info(f"Verification pipeline completed in {(completed_at - started_at).total_seconds():.2f}s")
            
            return self._create_summary(results, started_at, overall_success)
            
        except Exception as e:
            self.logger.error(f"Verification pipeline failed: {str(e)}")
            
            # Create error result
            error_result = VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                stage=VerificationStage.PIPELINE,
                language=context.language,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                error_message=f"Pipeline error: {str(e)}",
                error_details={"exception": str(e), "type": type(e).__name__}
            )
            
            return VerificationSummary(
                overall_success=False,
                total_stages=0,
                completed_stages=0,
                results=[error_result],
                started_at=started_at,
                completed_at=datetime.utcnow(),
                language=context.language,
                context=context
            )
    
    async def verify_multiple(self, contexts: List[VerificationContext]) -> List[VerificationSummary]:
        """
        Verify multiple contexts.
        
        Args:
            contexts: List of verification contexts
            
        Returns:
            List of verification summaries
        """
        if self.parallel_execution:
            # Run verifications in parallel
            tasks = [self.verify(context) for context in contexts]
            return await asyncio.gather(*tasks, return_exceptions=False)
        else:
            # Run verifications sequentially
            summaries = []
            for context in contexts:
                summary = await self.verify(context)
                summaries.append(summary)
            return summaries
    
    async def is_available(self) -> bool:
        """Check if the verification pipeline is available."""
        try:
            # Check if at least one verifier is available for each enabled stage
            compiler_available = False
            test_available = False
            
            if self.enable_compiler_verification:
                for verifier in self._compiler_verifiers.values():
                    if await verifier.is_available():
                        compiler_available = True
                        break
                        
                if not compiler_available:
                    self.logger.warning("No compiler verifiers available")
                    return False
            else:
                compiler_available = True
            
            if self.enable_test_verification:
                for verifier in self._test_verifiers.values():
                    if await verifier.is_available():
                        test_available = True
                        break
                        
                if not test_available:
                    self.logger.warning("No test verifiers available")
                    return False
            else:
                test_available = True
            
            return compiler_available and test_available
            
        except Exception as e:
            self.logger.error(f"Error checking pipeline availability: {str(e)}")
            return False
    
    def get_supported_languages(self) -> Set[LanguageType]:
        """Get all supported languages across all verifiers."""
        supported = set()
        
        for verifier in self._compiler_verifiers.values():
            supported.update(verifier.supported_languages)
        
        for verifier in self._test_verifiers.values():
            supported.update(verifier.supported_languages)
        
        return supported
    
    async def _run_compiler_verification(self, context: VerificationContext) -> VerificationResult:
        """Run compiler verification stage."""
        try:
            verifier = self._compiler_verifiers.get(context.language)
            
            if not verifier:
                return VerificationResult(
                    success=False,
                    status=VerificationStatus.ERROR,
                    stage=VerificationStage.COMPILATION,
                    language=context.language,
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                    error_message=f"No compiler verifier available for {context.language.value}",
                    error_details={"missing_verifier": context.language.value}
                )
            
            # Check if verifier is available
            if not await verifier.is_available():
                return VerificationResult(
                    success=False,
                    status=VerificationStatus.ERROR,
                    stage=VerificationStage.COMPILATION,
                    language=context.language,
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                    error_message=f"Compiler verifier for {context.language.value} is not available",
                    error_details={"unavailable_verifier": context.language.value}
                )
            
            self.logger.info(f"Running compiler verification for {context.language.value}")
            return await verifier.verify(context)
            
        except Exception as e:
            self.logger.error(f"Compiler verification failed: {str(e)}")
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                stage=VerificationStage.COMPILATION,
                language=context.language,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                error_message=f"Compiler verification error: {str(e)}",
                error_details={"exception": str(e)}
            )
    
    async def _run_test_verification(self, context: VerificationContext) -> VerificationResult:
        """Run test verification stage."""
        try:
            verifier = self._test_verifiers.get(context.language)
            
            if not verifier:
                return VerificationResult(
                    success=True,
                    status=VerificationStatus.SKIPPED,
                    stage=VerificationStage.TESTING,
                    language=context.language,
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                    output=f"No test verifier available for {context.language.value}",
                    metrics={"reason": "no_verifier_available"}
                )
            
            # Check if verifier is available
            if not await verifier.is_available():
                return VerificationResult(
                    success=True,
                    status=VerificationStatus.SKIPPED,
                    stage=VerificationStage.TESTING,
                    language=context.language,
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                    output=f"Test verifier for {context.language.value} is not available",
                    warnings=[f"Test framework not installed for {context.language.value}"],
                    metrics={"reason": "verifier_unavailable"}
                )
            
            self.logger.info(f"Running test verification for {context.language.value}")
            return await verifier.verify(context)
            
        except Exception as e:
            self.logger.error(f"Test verification failed: {str(e)}")
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                stage=VerificationStage.TESTING,
                language=context.language,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                error_message=f"Test verification error: {str(e)}",
                error_details={"exception": str(e)}
            )
    
    def _create_summary(
        self, 
        results: List[VerificationResult], 
        started_at: datetime, 
        overall_success: bool
    ) -> VerificationSummary:
        """Create a verification summary from results."""
        completed_at = datetime.utcnow()
        
        # Calculate stages
        total_stages = len(results)
        completed_stages = len([r for r in results if r.status != VerificationStatus.ERROR])
        
        # Extract language and context from first result
        language = results[0].language if results else LanguageType.PYTHON
        context = getattr(results[0], 'context', None) if results else None
        
        # Aggregate metrics
        all_metrics = {}
        all_warnings = []
        
        for result in results:
            if result.metrics:
                all_metrics.update(result.metrics)
            if result.warnings:
                all_warnings.extend(result.warnings)
        
        # Add summary metrics
        all_metrics.update({
            "total_execution_time": (completed_at - started_at).total_seconds(),
            "stages_completed": completed_stages,
            "stages_total": total_stages,
            "pipeline_success_rate": completed_stages / total_stages if total_stages > 0 else 0.0
        })
        
        return VerificationSummary(
            overall_success=overall_success,
            total_stages=total_stages,
            completed_stages=completed_stages,
            results=results,
            started_at=started_at,
            completed_at=completed_at,
            language=language,
            context=context,
            metrics=all_metrics,
            warnings=all_warnings,
            config={
                "stop_on_compiler_failure": self.stop_on_compiler_failure,
                "parallel_execution": self.parallel_execution,
                "compiler_enabled": self.enable_compiler_verification,
                "test_enabled": self.enable_test_verification
            }
        )