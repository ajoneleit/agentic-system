"""Verification pipeline orchestrator."""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from src.core.interfaces import Artifact, ArtifactType, Task, TaskStatus
from src.utils.app_logging import get_logger

from .compiler_verifiers import get_verifier_for_language
from .test_verifiers import PythonTestVerifier, JavaScriptTestVerifier
from .verifier_base import (
    BaseVerifier,
    VerificationConfig,
    VerificationError,
    VerificationResult,
    VerificationType,
)


logger = get_logger(__name__)


@dataclass
class PipelineResult:
    """Results from running the verification pipeline."""
    
    total_artifacts: int = 0
    verified_artifacts: int = 0
    failed_artifacts: int = 0
    skipped_artifacts: int = 0
    
    verification_results: Dict[UUID, List[VerificationResult]] = field(default_factory=dict)
    artifact_status: Dict[UUID, str] = field(default_factory=dict)  # passed, failed, skipped
    
    execution_time: float = 0.0
    started_at: datetime = field(default_factory=lambda: datetime.now())
    completed_at: Optional[datetime] = None
    
    # Summary by verification type
    syntax_checks: int = 0
    syntax_passed: int = 0
    compilation_checks: int = 0
    compilation_passed: int = 0
    test_executions: int = 0
    tests_passed: int = 0
    
    # Critical failures that should block deployment
    critical_failures: List[str] = field(default_factory=list)
    
    # Suggestions for improvement
    suggestions: List[str] = field(default_factory=list)
    
    def add_result(self, artifact_id: UUID, result: VerificationResult) -> None:
        """Add a verification result."""
        if artifact_id not in self.verification_results:
            self.verification_results[artifact_id] = []
        self.verification_results[artifact_id].append(result)
        
        # Update counters
        if result.verification_type == VerificationType.SYNTAX:
            self.syntax_checks += 1
            if result.success:
                self.syntax_passed += 1
        elif result.verification_type == VerificationType.COMPILATION:
            self.compilation_checks += 1
            if result.success:
                self.compilation_passed += 1
        elif result.verification_type == VerificationType.TEST:
            self.test_executions += 1
            if result.success:
                self.tests_passed += 1
        
        # Update artifact status
        if not result.success:
            self.artifact_status[artifact_id] = "failed"
            if result.verification_type in [VerificationType.SYNTAX, VerificationType.COMPILATION]:
                self.critical_failures.append(
                    f"Artifact {artifact_id} failed {result.verification_type.value} check"
                )
    
    def complete(self) -> None:
        """Mark pipeline as complete."""
        self.completed_at = datetime.now()
        if self.started_at:
            self.execution_time = (self.completed_at - self.started_at).total_seconds()
        
        # Count final artifact statuses
        for artifact_id, results in self.verification_results.items():
            if artifact_id not in self.artifact_status:
                # If no failures recorded, mark as passed
                self.artifact_status[artifact_id] = "passed"
        
        status_counts = defaultdict(int)
        for status in self.artifact_status.values():
            status_counts[status] += 1
        
        self.verified_artifacts = status_counts["passed"]
        self.failed_artifacts = status_counts["failed"]
        self.skipped_artifacts = status_counts["skipped"]
    
    @property
    def success(self) -> bool:
        """Check if pipeline succeeded overall."""
        return len(self.critical_failures) == 0 and self.failed_artifacts == 0


class VerificationPipeline:
    """Orchestrates the verification process for multiple artifacts."""
    
    def __init__(self, config: Optional[VerificationConfig] = None):
        """Initialize the verification pipeline.
        
        Args:
            config: Verification configuration
        """
        self.config = config or VerificationConfig()
        self._verifiers: Dict[str, List[BaseVerifier]] = self._initialize_verifiers()
    
    def _initialize_verifiers(self) -> Dict[str, List[BaseVerifier]]:
        """Initialize available verifiers grouped by language."""
        verifiers = defaultdict(list)
        
        # Add compiler verifiers
        for lang in ["python", "javascript", "typescript"]:
            compiler_verifier = get_verifier_for_language(lang, self.config)
            if compiler_verifier:
                verifiers[lang].append(compiler_verifier)
        
        # Add test verifiers
        verifiers["python"].append(PythonTestVerifier(self.config))
        verifiers["javascript"].append(JavaScriptTestVerifier(self.config))
        verifiers["typescript"].append(JavaScriptTestVerifier(self.config))  # JS test runner works for TS
        
        return verifiers
    
    async def verify_artifacts(
        self,
        artifacts: List[Artifact],
        verification_config: Optional[VerificationConfig] = None
    ) -> PipelineResult:
        """Verify multiple artifacts through the pipeline.
        
        Args:
            artifacts: List of artifacts to verify
            verification_config: Optional override configuration
            
        Returns:
            Pipeline execution result
        """
        config = verification_config or self.config
        result = PipelineResult(total_artifacts=len(artifacts))
        
        logger.info(f"Starting verification pipeline for {len(artifacts)} artifacts")
        
        try:
            # Group artifacts by dependencies and type
            artifact_groups = self._group_artifacts(artifacts)
            
            # Verify each group in order
            for group_name, group_artifacts in artifact_groups:
                logger.info(f"Verifying {group_name} group with {len(group_artifacts)} artifacts")
                
                # Run verifications in parallel within each group
                await self._verify_group(group_artifacts, config, result)
                
                # Stop if critical failures in compilation
                if group_name in ["source", "compilation"] and result.critical_failures:
                    logger.warning("Critical failures detected, stopping pipeline")
                    break
            
            # Generate overall suggestions
            self._generate_pipeline_suggestions(result)
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            result.critical_failures.append(f"Pipeline execution failed: {str(e)}")
        
        result.complete()
        logger.info(
            f"Pipeline complete: {result.verified_artifacts} passed, "
            f"{result.failed_artifacts} failed, {result.skipped_artifacts} skipped"
        )
        
        return result
    
    def _group_artifacts(self, artifacts: List[Artifact]) -> List[Tuple[str, List[Artifact]]]:
        """Group artifacts by type and dependencies for ordered verification."""
        groups = []
        
        # First verify source code
        source_artifacts = [a for a in artifacts if a.type == ArtifactType.SOURCE_CODE]
        if source_artifacts:
            groups.append(("source", source_artifacts))
        
        # Then verify tests (which may depend on source)
        test_artifacts = [a for a in artifacts if a.type == ArtifactType.TEST_CODE]
        if test_artifacts:
            groups.append(("test", test_artifacts))
        
        # Other artifact types
        other_artifacts = [
            a for a in artifacts 
            if a.type not in [ArtifactType.SOURCE_CODE, ArtifactType.TEST_CODE]
        ]
        if other_artifacts:
            groups.append(("other", other_artifacts))
        
        return groups
    
    async def _verify_group(
        self,
        artifacts: List[Artifact],
        config: VerificationConfig,
        result: PipelineResult
    ) -> None:
        """Verify a group of artifacts in parallel."""
        # Create verification tasks
        tasks = []
        
        for artifact in artifacts:
            if await self._should_verify(artifact, config):
                task = self._verify_single_artifact(artifact, config, result)
                tasks.append(task)
            else:
                result.skipped_artifacts += 1
                result.artifact_status[artifact.id] = "skipped"
        
        # Run verifications in parallel with concurrency limit
        if tasks:
            # Use semaphore to limit concurrency
            semaphore = asyncio.Semaphore(config.max_parallel_verifications)
            
            async def run_with_semaphore(task):
                async with semaphore:
                    return await task
            
            await asyncio.gather(*[run_with_semaphore(task) for task in tasks])
    
    async def _should_verify(self, artifact: Artifact, config: VerificationConfig) -> bool:
        """Check if an artifact should be verified."""
        # Skip if no content or path
        if not artifact.content and (not artifact.path or not artifact.path.exists()):
            return False
        
        # Skip based on configuration
        if artifact.type == ArtifactType.SOURCE_CODE:
            return config.enable_syntax_check or config.enable_compilation
        elif artifact.type == ArtifactType.TEST_CODE:
            return config.enable_tests
        
        return False
    
    async def _verify_single_artifact(
        self,
        artifact: Artifact,
        config: VerificationConfig,
        result: PipelineResult
    ) -> None:
        """Verify a single artifact with appropriate verifiers."""
        language = self._detect_language(artifact)
        if not language:
            logger.warning(f"Could not detect language for artifact {artifact.id}")
            result.skipped_artifacts += 1
            result.artifact_status[artifact.id] = "skipped"
            return
        
        verifiers = self._verifiers.get(language, [])
        if not verifiers:
            logger.warning(f"No verifiers available for language: {language}")
            result.skipped_artifacts += 1
            result.artifact_status[artifact.id] = "skipped"
            return
        
        # Run appropriate verifiers based on artifact type and config
        for verifier in verifiers:
            should_run = False
            
            if artifact.type == ArtifactType.SOURCE_CODE:
                if isinstance(verifier.verification_type, VerificationType):
                    if verifier.verification_type == VerificationType.SYNTAX and config.enable_syntax_check:
                        should_run = True
                    elif verifier.verification_type == VerificationType.COMPILATION and config.enable_compilation:
                        should_run = True
            elif artifact.type == ArtifactType.TEST_CODE:
                if verifier.verification_type == VerificationType.TEST and config.enable_tests:
                    should_run = True
            
            if should_run and await verifier.can_verify(artifact):
                try:
                    # Get context for verification (e.g., related source files for tests)
                    context = await self._get_verification_context(artifact, verifier)
                    
                    # Run verification
                    verification_result = await verifier.verify(artifact, context)
                    
                    # Add to results
                    result.add_result(artifact.id, verification_result)
                    
                    # Stop on critical failures
                    if not verification_result.success and verifier.verification_type in [
                        VerificationType.SYNTAX,
                        VerificationType.COMPILATION
                    ]:
                        logger.warning(
                            f"Critical failure in {verifier.name} for artifact {artifact.id}"
                        )
                        break
                        
                except Exception as e:
                    logger.error(f"Verifier {verifier.name} failed: {e}")
                    error_result = VerificationResult(
                        success=False,
                        verification_type=verifier.verification_type,
                        artifact_id=artifact.id,
                        verifier_name=verifier.name,
                        error_messages=[f"Verifier error: {str(e)}"],
                    )
                    result.add_result(artifact.id, error_result)
    
    def _detect_language(self, artifact: Artifact) -> Optional[str]:
        """Detect the programming language of an artifact."""
        if artifact.path:
            extension_map = {
                ".py": "python",
                ".js": "javascript",
                ".mjs": "javascript",
                ".cjs": "javascript",
                ".ts": "typescript",
                ".tsx": "typescript",
            }
            return extension_map.get(artifact.path.suffix.lower())
        
        # Try to detect from content
        if artifact.content:
            if "def " in artifact.content or "import " in artifact.content:
                return "python"
            elif "function " in artifact.content or "const " in artifact.content:
                return "javascript"
        
        return None
    
    async def _get_verification_context(
        self,
        artifact: Artifact,
        verifier: BaseVerifier
    ) -> Dict[str, Any]:
        """Get context needed for verification."""
        context = await verifier.get_verification_context(artifact)
        
        # Add related artifacts for test verification
        if artifact.type == ArtifactType.TEST_CODE:
            # In a real implementation, this would fetch related source artifacts
            # from the artifact manager based on dependencies
            context["source_artifacts"] = []
        
        return context
    
    def _generate_pipeline_suggestions(self, result: PipelineResult) -> None:
        """Generate overall suggestions based on pipeline results."""
        if result.syntax_checks > 0 and result.syntax_passed < result.syntax_checks:
            result.suggestions.append(
                "Fix syntax errors before proceeding with other verifications"
            )
        
        if result.compilation_checks > 0 and result.compilation_passed < result.compilation_checks:
            result.suggestions.append(
                "Ensure code compiles successfully before running tests"
            )
        
        if result.test_executions > 0:
            test_pass_rate = result.tests_passed / result.test_executions
            if test_pass_rate < 1.0:
                result.suggestions.append(
                    f"Improve test pass rate (currently {test_pass_rate:.1%})"
                )
        
        # Check coverage from test results
        total_coverage = 0.0
        coverage_count = 0
        
        for artifact_results in result.verification_results.values():
            for verification_result in artifact_results:
                if verification_result.metrics.coverage_percent > 0:
                    total_coverage += verification_result.metrics.coverage_percent
                    coverage_count += 1
        
        if coverage_count > 0:
            avg_coverage = total_coverage / coverage_count
            if avg_coverage < self.config.test_coverage_threshold * 100:
                result.suggestions.append(
                    f"Increase test coverage (currently {avg_coverage:.1f}%, "
                    f"target {self.config.test_coverage_threshold * 100:.0f}%)"
                )


async def verify_task_artifacts(
    task: Task,
    artifact_manager,
    config: Optional[VerificationConfig] = None
) -> Tuple[bool, List[VerificationResult]]:
    """Verify all artifacts associated with a task.
    
    Args:
        task: The task whose artifacts to verify
        artifact_manager: Artifact manager to fetch artifacts
        config: Optional verification configuration
        
    Returns:
        Tuple of (success, list of verification results)
    """
    # Fetch task artifacts
    artifacts = []
    for artifact_id in task.artifacts:
        artifact = await artifact_manager.get_artifact(artifact_id)
        if artifact:
            artifacts.append(artifact)
    
    if not artifacts:
        logger.info(f"No artifacts to verify for task {task.id}")
        return True, []
    
    # Run verification pipeline
    pipeline = VerificationPipeline(config)
    result = await pipeline.verify_artifacts(artifacts)
    
    # Extract all verification results
    all_results = []
    for artifact_results in result.verification_results.values():
        all_results.extend(artifact_results)
    
    return result.success, all_results