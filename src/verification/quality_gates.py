"""Quality gates system for validating Claude CLI outputs.

This module implements multi-stage quality validation for code generated
through Claude CLI, ensuring production-ready outputs before acceptance.
"""

import ast
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from structlog import get_logger

from src.core.exceptions import QualityCheckError, VerificationError


logger = get_logger(__name__)


@dataclass
class QualityMetrics:
    """Quality metrics for code evaluation."""
    
    code_quality_score: float  # 0.0 to 1.0
    test_coverage_estimate: float  # 0.0 to 1.0
    security_score: float  # 0.0 to 1.0
    performance_score: float  # 0.0 to 1.0
    documentation_score: float  # 0.0 to 1.0
    complexity_score: float  # 0.0 to 1.0
    
    @property
    def overall_score(self) -> float:
        """Calculate weighted overall score."""
        weights = {
            "code_quality": 0.25,
            "test_coverage": 0.20,
            "security": 0.20,
            "performance": 0.15,
            "documentation": 0.10,
            "complexity": 0.10
        }
        
        total = (
            self.code_quality_score * weights["code_quality"] +
            self.test_coverage_estimate * weights["test_coverage"] +
            self.security_score * weights["security"] +
            self.performance_score * weights["performance"] +
            self.documentation_score * weights["documentation"] +
            self.complexity_score * weights["complexity"]
        )
        
        return total


@dataclass
class QualityIssue:
    """Represents a quality issue found during validation."""
    
    severity: str  # "critical", "high", "medium", "low"
    category: str  # "security", "performance", "style", etc.
    description: str
    file: Optional[str] = None
    line: Optional[int] = None
    suggestion: Optional[str] = None


@dataclass
class QualityResult:
    """Result of quality validation."""
    
    passed: bool
    metrics: QualityMetrics
    issues: List[QualityIssue]
    timestamp: datetime
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "passed": self.passed,
            "metrics": {
                "code_quality_score": self.metrics.code_quality_score,
                "test_coverage_estimate": self.metrics.test_coverage_estimate,
                "security_score": self.metrics.security_score,
                "performance_score": self.metrics.performance_score,
                "documentation_score": self.metrics.documentation_score,
                "complexity_score": self.metrics.complexity_score,
                "overall_score": self.metrics.overall_score
            },
            "issues": [
                {
                    "severity": issue.severity,
                    "category": issue.category,
                    "description": issue.description,
                    "file": issue.file,
                    "line": issue.line,
                    "suggestion": issue.suggestion
                }
                for issue in self.issues
            ],
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


class CodeQualityAnalyzer:
    """Analyzes code quality metrics."""
    
    def analyze_python_code(self, code: str, filename: str = "code.py") -> Tuple[float, List[QualityIssue]]:
        """Analyze Python code quality.
        
        Args:
            code: Python code to analyze
            filename: Name of the file
            
        Returns:
            Tuple of (quality_score, issues)
        """
        issues = []
        score = 1.0
        
        try:
            # Parse AST
            tree = ast.parse(code)
            
            # Check for docstrings
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    if not ast.get_docstring(node):
                        issues.append(QualityIssue(
                            severity="medium",
                            category="documentation",
                            description=f"Missing docstring for {node.name}",
                            file=filename,
                            line=node.lineno,
                            suggestion=f"Add a docstring describing what {node.name} does"
                        ))
                        score -= 0.05
            
            # Check for proper error handling
            has_error_handling = any(
                isinstance(node, ast.Try)
                for node in ast.walk(tree)
            )
            
            if not has_error_handling and len(code.splitlines()) > 20:
                issues.append(QualityIssue(
                    severity="high",
                    category="error_handling",
                    description="No error handling found in code",
                    file=filename,
                    suggestion="Add try-except blocks for error-prone operations"
                ))
                score -= 0.15
            
            # Check for type hints (simple check)
            functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            functions_with_hints = sum(1 for func in functions if func.returns or any(arg.annotation for arg in func.args.args))
            
            if functions and functions_with_hints / len(functions) < 0.5:
                issues.append(QualityIssue(
                    severity="low",
                    category="type_hints",
                    description="Less than 50% of functions have type hints",
                    file=filename,
                    suggestion="Add type hints to improve code clarity"
                ))
                score -= 0.10
                
        except SyntaxError as e:
            issues.append(QualityIssue(
                severity="critical",
                category="syntax",
                description=f"Syntax error: {str(e)}",
                file=filename,
                line=e.lineno,
                suggestion="Fix the syntax error before proceeding"
            ))
            score = 0.0
            
        return max(0.0, score), issues
    
    def analyze_complexity(self, code: str) -> float:
        """Analyze code complexity (simplified).
        
        Args:
            code: Code to analyze
            
        Returns:
            Complexity score (1.0 = low complexity, 0.0 = high complexity)
        """
        try:
            tree = ast.parse(code)
            
            # Count nested levels
            max_depth = 0
            
            def get_depth(node, depth=0):
                nonlocal max_depth
                max_depth = max(max_depth, depth)
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.For, ast.While, ast.If, ast.With, ast.Try)):
                        get_depth(child, depth + 1)
                    else:
                        get_depth(child, depth)
            
            get_depth(tree)
            
            # Penalize deep nesting
            if max_depth <= 3:
                return 1.0
            elif max_depth <= 5:
                return 0.8
            elif max_depth <= 7:
                return 0.6
            else:
                return 0.4
                
        except Exception:
            return 0.5  # Default for unparseable code


class SecurityScanner:
    """Scans code for security vulnerabilities."""
    
    # Common security patterns to check
    DANGEROUS_PATTERNS = {
        r'eval\s*\(': ("Use of eval() is dangerous", "critical"),
        r'exec\s*\(': ("Use of exec() is dangerous", "critical"),
        r'__import__\s*\(': ("Dynamic imports can be dangerous", "high"),
        r'pickle\.loads?\s*\(': ("Pickle can execute arbitrary code", "high"),
        r'subprocess.*shell\s*=\s*True': ("Shell injection risk", "critical"),
        r'os\.system\s*\(': ("Command injection risk", "high"),
        r'\.format\s*\(\{0\}': ("Format string vulnerability", "medium"),
        r'request\.\w+\[': ("Potential injection if not validated", "medium"),
    }
    
    def scan_code(self, code: str, filename: str = "code.py") -> Tuple[float, List[QualityIssue]]:
        """Scan code for security issues.
        
        Args:
            code: Code to scan
            filename: Name of the file
            
        Returns:
            Tuple of (security_score, issues)
        """
        issues = []
        score = 1.0
        
        for pattern, (description, severity) in self.DANGEROUS_PATTERNS.items():
            matches = list(re.finditer(pattern, code, re.IGNORECASE))
            for match in matches:
                line_no = code[:match.start()].count('\n') + 1
                issues.append(QualityIssue(
                    severity=severity,
                    category="security",
                    description=description,
                    file=filename,
                    line=line_no,
                    suggestion="Review and replace with safer alternatives"
                ))
                
                # Deduct score based on severity
                if severity == "critical":
                    score -= 0.25
                elif severity == "high":
                    score -= 0.15
                elif severity == "medium":
                    score -= 0.10
                else:
                    score -= 0.05
        
        return max(0.0, score), issues


class TestCoverageEstimator:
    """Estimates test coverage from code analysis."""
    
    def estimate_coverage(self, code: str, test_code: str = "") -> float:
        """Estimate test coverage.
        
        Args:
            code: Source code
            test_code: Test code
            
        Returns:
            Coverage estimate (0.0 to 1.0)
        """
        try:
            # Parse source code
            tree = ast.parse(code)
            
            # Count testable items
            functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            
            testable_items = len(functions) + len(classes)
            
            if testable_items == 0:
                return 1.0  # No testable items
            
            # If we have test code, analyze it
            if test_code:
                test_tree = ast.parse(test_code)
                test_functions = [
                    node for node in ast.walk(test_tree)
                    if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
                ]
                
                # Rough estimate: assume each test covers one item
                coverage = min(1.0, len(test_functions) / testable_items)
                return coverage
            
            # No test code provided
            return 0.0
            
        except Exception:
            return 0.0


class QualityGateSystem:
    """Main quality gate system for validating outputs."""
    
    def __init__(self, min_quality_score: float = 0.8):
        """Initialize quality gate system.
        
        Args:
            min_quality_score: Minimum acceptable quality score
        """
        self.min_quality_score = min_quality_score
        self.code_analyzer = CodeQualityAnalyzer()
        self.security_scanner = SecurityScanner()
        self.coverage_estimator = TestCoverageEstimator()
        
        logger.info(
            "Quality gate system initialized",
            min_quality_score=min_quality_score
        )
    
    async def validate_cli_output(
        self,
        output: str,
        task: Dict[str, Any],
        requirements: Optional[Dict[str, Any]] = None
    ) -> QualityResult:
        """Validate Claude CLI output through quality gates.
        
        Args:
            output: CLI output to validate
            task: Task information
            requirements: Quality requirements (optional)
            
        Returns:
            Quality validation result
        """
        issues = []
        
        # Default requirements
        if requirements is None:
            requirements = {
                "min_code_quality": 0.8,
                "min_security_score": 0.9,
                "min_test_coverage": 0.7,
                "max_complexity": 0.6  # Lower is more complex
            }
        
        # Extract code from output
        code_blocks = self._extract_code_blocks(output)
        
        if not code_blocks:
            return QualityResult(
                passed=False,
                metrics=QualityMetrics(0, 0, 0, 0, 0, 0),
                issues=[QualityIssue(
                    severity="critical",
                    category="output",
                    description="No code found in output",
                    suggestion="Ensure the output contains properly formatted code blocks"
                )],
                timestamp=datetime.utcnow(),
                metadata={"task": task}
            )
        
        # Analyze main code block
        main_code = code_blocks[0]["code"]
        language = code_blocks[0]["language"]
        
        # Only analyze Python code for now
        if language != "python":
            logger.warning(f"Language {language} not fully supported for quality analysis")
        
        # Code quality analysis
        quality_score, quality_issues = self.code_analyzer.analyze_python_code(main_code)
        issues.extend(quality_issues)
        
        # Security scanning
        security_score, security_issues = self.security_scanner.scan_code(main_code)
        issues.extend(security_issues)
        
        # Complexity analysis
        complexity_score = self.code_analyzer.analyze_complexity(main_code)
        
        # Test coverage estimation
        test_code = self._extract_test_code(code_blocks)
        coverage_score = self.coverage_estimator.estimate_coverage(main_code, test_code)
        
        # Documentation score (simple check)
        doc_score = self._calculate_documentation_score(main_code)
        
        # Performance score (placeholder - would need more sophisticated analysis)
        performance_score = 0.9  # Default high score
        
        # Create metrics
        metrics = QualityMetrics(
            code_quality_score=quality_score,
            test_coverage_estimate=coverage_score,
            security_score=security_score,
            performance_score=performance_score,
            documentation_score=doc_score,
            complexity_score=complexity_score
        )
        
        # Check against requirements
        passed = (
            quality_score >= requirements.get("min_code_quality", 0.8) and
            security_score >= requirements.get("min_security_score", 0.9) and
            coverage_score >= requirements.get("min_test_coverage", 0.7) and
            complexity_score >= requirements.get("max_complexity", 0.6)
        )
        
        # Log result
        logger.info(
            "Quality validation completed",
            passed=passed,
            overall_score=metrics.overall_score,
            issues_count=len(issues),
            task_name=task.get("name", "unknown")
        )
        
        return QualityResult(
            passed=passed,
            metrics=metrics,
            issues=issues,
            timestamp=datetime.utcnow(),
            metadata={
                "task": task,
                "requirements": requirements,
                "code_blocks": len(code_blocks)
            }
        )
    
    def _extract_code_blocks(self, output: str) -> List[Dict[str, str]]:
        """Extract code blocks from output.
        
        Args:
            output: Text containing code blocks
            
        Returns:
            List of code blocks with language and content
        """
        code_blocks = []
        
        # Match ```language\ncode\n``` patterns
        pattern = r'```(\w+)?\n(.*?)\n```'
        matches = re.finditer(pattern, output, re.DOTALL)
        
        for match in matches:
            language = match.group(1) or "text"
            code = match.group(2)
            code_blocks.append({
                "language": language,
                "code": code
            })
        
        return code_blocks
    
    def _extract_test_code(self, code_blocks: List[Dict[str, str]]) -> str:
        """Extract test code from code blocks.
        
        Args:
            code_blocks: List of code blocks
            
        Returns:
            Combined test code
        """
        test_code_parts = []
        
        for block in code_blocks:
            code = block["code"]
            # Check if it looks like test code
            if "test_" in code or "assert" in code or "unittest" in code or "pytest" in code:
                test_code_parts.append(code)
        
        return "\n\n".join(test_code_parts)
    
    def _calculate_documentation_score(self, code: str) -> float:
        """Calculate documentation score.
        
        Args:
            code: Code to analyze
            
        Returns:
            Documentation score (0.0 to 1.0)
        """
        try:
            tree = ast.parse(code)
            
            total_items = 0
            documented_items = 0
            
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    total_items += 1
                    if ast.get_docstring(node):
                        documented_items += 1
            
            if total_items == 0:
                return 1.0
                
            return documented_items / total_items
            
        except Exception:
            return 0.5  # Default for unparseable code
    
    async def generate_feedback_prompt(
        self,
        quality_result: QualityResult,
        original_task: Dict[str, Any]
    ) -> str:
        """Generate improvement prompt for retry based on quality issues.
        
        Args:
            quality_result: Quality validation result
            original_task: Original task information
            
        Returns:
            Feedback prompt for improvement
        """
        if quality_result.passed:
            return ""  # No feedback needed
        
        sections = [
            f"# Task Improvement Required: {original_task.get('name', 'Task')}",
            "",
            "The previous attempt did not meet quality standards. Please address the following issues:",
            ""
        ]
        
        # Group issues by category
        issues_by_category = {}
        for issue in quality_result.issues:
            if issue.category not in issues_by_category:
                issues_by_category[issue.category] = []
            issues_by_category[issue.category].append(issue)
        
        # Add issues by category
        for category, category_issues in issues_by_category.items():
            sections.append(f"## {category.title()} Issues:")
            for issue in category_issues:
                sections.append(f"- **{issue.severity.upper()}**: {issue.description}")
                if issue.file and issue.line:
                    sections.append(f"  Location: {issue.file}:{issue.line}")
                if issue.suggestion:
                    sections.append(f"  Suggestion: {issue.suggestion}")
            sections.append("")
        
        # Add metrics summary
        sections.extend([
            "## Quality Metrics Summary:",
            f"- Code Quality: {quality_result.metrics.code_quality_score:.2f} (minimum: 0.80)",
            f"- Security: {quality_result.metrics.security_score:.2f} (minimum: 0.90)",
            f"- Test Coverage: {quality_result.metrics.test_coverage_estimate:.2f} (minimum: 0.70)",
            f"- Complexity: {quality_result.metrics.complexity_score:.2f} (lower is more complex)",
            f"- Documentation: {quality_result.metrics.documentation_score:.2f}",
            f"- Overall Score: {quality_result.metrics.overall_score:.2f}",
            "",
            "## Requirements:",
            "Please revise your solution to address all issues above while maintaining:",
            "1. All original functional requirements",
            "2. Proper error handling and validation",
            "3. Comprehensive test coverage",
            "4. Clear documentation and type hints",
            "5. Secure coding practices",
            ""
        ])
        
        return "\n".join(sections)