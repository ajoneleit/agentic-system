"""Repair analyzer for analyzing verification failures and suggesting fixes."""

import ast
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.core.interfaces import Artifact, ArtifactType
from src.utils.app_logging import get_logger

from .verifier_base import VerificationResult, VerificationType


logger = get_logger(__name__)


@dataclass
class RepairSuggestion:
    """A suggestion for repairing a verification failure."""
    
    # Required fields (no defaults)
    artifact_id: str
    failure_type: str  # syntax, compilation, test, etc.
    severity: str  # critical, major, minor
    issue_description: str
    suggestion: str
    repair_prompt: str  # Prompt for AI to fix the issue
    
    # Optional fields (with defaults)
    error_location: Optional[Dict[str, Any]] = None  # line, column, file
    code_snippet: Optional[str] = None
    related_errors: List[str] = field(default_factory=list)
    confidence: float = 0.8  # How confident we are in the suggestion
    created_at: datetime = field(default_factory=lambda: datetime.now())


class RepairAnalyzer:
    """Analyzes verification failures and generates repair suggestions."""
    
    def __init__(self):
        """Initialize the repair analyzer."""
        self.syntax_patterns = self._compile_syntax_patterns()
        self.test_patterns = self._compile_test_patterns()
    
    def _compile_syntax_patterns(self) -> Dict[str, re.Pattern]:
        """Compile common syntax error patterns."""
        return {
            "missing_colon": re.compile(r"expected ':'"),
            "indentation": re.compile(r"IndentationError|unexpected indent"),
            "missing_paren": re.compile(r"unmatched '\)'|unexpected EOF"),
            "invalid_syntax": re.compile(r"invalid syntax"),
            "undefined_name": re.compile(r"name '(\w+)' is not defined"),
            "import_error": re.compile(r"ImportError|No module named"),
        }
    
    def _compile_test_patterns(self) -> Dict[str, re.Pattern]:
        """Compile common test failure patterns."""
        return {
            "assertion": re.compile(r"AssertionError"),
            "type_error": re.compile(r"TypeError"),
            "value_error": re.compile(r"ValueError"),
            "attribute_error": re.compile(r"AttributeError"),
            "key_error": re.compile(r"KeyError"),
            "index_error": re.compile(r"IndexError"),
        }
    
    async def analyze_failure(
        self,
        artifact: Artifact,
        verification_result: VerificationResult
    ) -> Optional[RepairSuggestion]:
        """Analyze a verification failure and generate repair suggestion.
        
        Args:
            artifact: The artifact that failed verification
            verification_result: The verification result with failure details
            
        Returns:
            Repair suggestion or None if cannot analyze
        """
        if verification_result.success:
            return None
        
        # Route to appropriate analyzer based on verification type
        if verification_result.verification_type == VerificationType.SYNTAX:
            return await self.analyze_syntax_error(artifact, verification_result)
        elif verification_result.verification_type == VerificationType.COMPILATION:
            return await self.analyze_compilation_error(artifact, verification_result)
        elif verification_result.verification_type == VerificationType.TEST:
            return await self.analyze_test_failure(artifact, verification_result)
        else:
            logger.warning(
                f"No analyzer for verification type: {verification_result.verification_type}"
            )
            return None
    
    async def analyze_syntax_error(
        self,
        artifact: Artifact,
        result: VerificationResult
    ) -> Optional[RepairSuggestion]:
        """Analyze syntax errors and suggest fixes.
        
        Args:
            artifact: The artifact with syntax errors
            result: Verification result containing error details
            
        Returns:
            Repair suggestion
        """
        if not result.error_messages:
            return None
        
        # Analyze the first error (usually most important)
        primary_error = result.error_messages[0]
        
        # Extract error details
        error_location = result.details.get("syntax_error", {})
        line_number = error_location.get("line", 0)
        
        # Determine error type and suggestion
        suggestion_text = "Fix the syntax error"
        repair_prompt = f"Fix the following syntax error in {artifact.name}:\n{primary_error}"
        severity = "critical"
        
        # Check for specific patterns
        if self.syntax_patterns["missing_colon"].search(primary_error):
            suggestion_text = "Add missing colon at the end of the statement"
            repair_prompt += "\n\nThe error indicates a missing colon, likely after an if, for, while, def, or class statement."
        
        elif self.syntax_patterns["indentation"].search(primary_error):
            suggestion_text = "Fix indentation to match Python's requirements"
            repair_prompt += "\n\nThe error is related to indentation. Ensure consistent use of spaces (4 spaces per level) and proper alignment."
        
        elif self.syntax_patterns["missing_paren"].search(primary_error):
            suggestion_text = "Check for unmatched parentheses, brackets, or braces"
            repair_prompt += "\n\nThere's an unmatched parenthesis, bracket, or brace. Count opening and closing symbols."
        
        elif self.syntax_patterns["undefined_name"].search(primary_error):
            match = self.syntax_patterns["undefined_name"].search(primary_error)
            if match:
                name = match.group(1)
                suggestion_text = f"Define '{name}' or import it if it's from a module"
                repair_prompt += f"\n\nThe name '{name}' is not defined. Either define it, import it, or fix the typo."
        
        # Get code snippet around error
        code_snippet = None
        if artifact.content and line_number > 0:
            lines = artifact.content.splitlines()
            if line_number <= len(lines):
                # Get 3 lines before and after
                start = max(0, line_number - 4)
                end = min(len(lines), line_number + 3)
                snippet_lines = []
                for i in range(start, end):
                    prefix = ">>> " if i == line_number - 1 else "    "
                    snippet_lines.append(f"{prefix}{i+1}: {lines[i]}")
                code_snippet = "\n".join(snippet_lines)
        
        return RepairSuggestion(
            artifact_id=str(artifact.id),
            failure_type="syntax",
            severity=severity,
            issue_description=primary_error,
            error_location=error_location,
            suggestion=suggestion_text,
            repair_prompt=repair_prompt,
            code_snippet=code_snippet,
            related_errors=result.error_messages[1:],  # Other errors
        )
    
    async def analyze_compilation_error(
        self,
        artifact: Artifact,
        result: VerificationResult
    ) -> Optional[RepairSuggestion]:
        """Analyze compilation errors and suggest fixes.
        
        Args:
            artifact: The artifact with compilation errors
            result: Verification result containing error details
            
        Returns:
            Repair suggestion
        """
        if not result.error_messages:
            return None
        
        primary_error = result.error_messages[0]
        
        # Check for import errors
        if self.syntax_patterns["import_error"].search(primary_error):
            module_match = re.search(r"No module named '(\w+)'", primary_error)
            module_name = module_match.group(1) if module_match else "unknown"
            
            return RepairSuggestion(
                artifact_id=str(artifact.id),
                failure_type="compilation",
                severity="major",
                issue_description=primary_error,
                suggestion=f"Install missing module '{module_name}' or fix import statement",
                repair_prompt=f"""Fix the import error in {artifact.name}:
{primary_error}

Either:
1. Change the import to use a standard library module
2. Fix the import path if it's a local module
3. Remove the import if it's not needed""",
                related_errors=result.error_messages[1:],
            )
        
        # Generic compilation error
        return RepairSuggestion(
            artifact_id=str(artifact.id),
            failure_type="compilation",
            severity="major",
            issue_description=primary_error,
            suggestion="Fix the compilation error",
            repair_prompt=f"""Fix the compilation error in {artifact.name}:
{primary_error}

Ensure the code follows proper Python syntax and all imports are valid.""",
            related_errors=result.error_messages[1:],
        )
    
    async def analyze_test_failure(
        self,
        artifact: Artifact,
        result: VerificationResult
    ) -> Optional[RepairSuggestion]:
        """Analyze test failures and suggest fixes.
        
        Args:
            artifact: The artifact with test failures  
            result: Verification result containing test failure details
            
        Returns:
            Repair suggestion
        """
        if not result.error_messages:
            return None
        
        # Get test metrics
        failed_count = result.metrics.tests_failed
        total_count = result.metrics.tests_total
        
        # Analyze failure patterns
        failure_types = []
        for error in result.error_messages:
            for pattern_name, pattern in self.test_patterns.items():
                if pattern.search(error):
                    failure_types.append(pattern_name)
                    break
        
        # Determine most common failure type
        if failure_types:
            most_common = max(set(failure_types), key=failure_types.count)
            suggestion_map = {
                "assertion": "Review expected values in assertions",
                "type_error": "Check data types being passed to functions",
                "value_error": "Validate input values and edge cases",
                "attribute_error": "Ensure all object attributes exist",
                "key_error": "Check dictionary keys before access",
                "index_error": "Validate list/array indices",
            }
            suggestion_text = suggestion_map.get(most_common, "Fix the failing tests")
        else:
            suggestion_text = "Review and fix the failing test cases"
        
        # Create repair prompt
        repair_prompt = f"""Fix the failing tests in {artifact.name}.

Test Summary:
- {failed_count} out of {total_count} tests are failing
- Main issue types: {', '.join(set(failure_types)) if failure_types else 'Various'}

Failing tests:
"""
        
        # Add first few test failures
        test_results = result.details.get("test_results", [])
        failing_tests = [t for t in test_results if t.get("status") == "failed"][:3]
        
        for test in failing_tests:
            repair_prompt += f"\n- {test.get('name', 'Unknown test')}: {test.get('error', 'No error details')}"
        
        repair_prompt += """

Please fix the implementation to make all tests pass. Focus on:
1. Understanding what each test expects
2. Fixing the logic to meet test requirements
3. Handling edge cases properly"""
        
        return RepairSuggestion(
            artifact_id=str(artifact.id),
            failure_type="test",
            severity="major" if failed_count > total_count / 2 else "minor",
            issue_description=f"{failed_count} tests failing out of {total_count}",
            suggestion=suggestion_text,
            repair_prompt=repair_prompt,
            related_errors=result.error_messages,
            confidence=0.9 if failure_types else 0.7,
        )
    
    async def generate_repair_prompt(
        self,
        artifact: Artifact,
        suggestions: List[RepairSuggestion]
    ) -> str:
        """Generate a comprehensive repair prompt for an artifact.
        
        Args:
            artifact: The artifact to repair
            suggestions: List of repair suggestions
            
        Returns:
            Complete repair prompt for AI
        """
        if not suggestions:
            return ""
        
        # Start with artifact context
        prompt = f"""Please repair the following code file: {artifact.name}

Current code:
```{self._detect_language(artifact)}
{artifact.content}
```

Issues found:
"""
        
        # Add each issue
        for i, suggestion in enumerate(suggestions, 1):
            prompt += f"\n{i}. {suggestion.issue_description}"
            if suggestion.error_location:
                line = suggestion.error_location.get("line")
                if line:
                    prompt += f" (line {line})"
            prompt += f"\n   Suggestion: {suggestion.suggestion}"
        
        # Add repair instructions
        prompt += "\n\nPlease fix all the issues above and return the complete corrected code."
        prompt += "\nMake sure to:"
        prompt += "\n- Fix all syntax errors"
        prompt += "\n- Ensure the code compiles/runs without errors"
        prompt += "\n- Make all tests pass (if applicable)"
        prompt += "\n- Maintain the original functionality"
        prompt += "\n- Keep the code clean and well-formatted"
        
        return prompt
    
    def _detect_language(self, artifact: Artifact) -> str:
        """Detect programming language for syntax highlighting."""
        if artifact.path:
            extension_map = {
                ".py": "python",
                ".js": "javascript",
                ".ts": "typescript",
                ".java": "java",
                ".go": "go",
                ".rs": "rust",
                ".cpp": "cpp",
                ".c": "c",
            }
            return extension_map.get(artifact.path.suffix.lower(), "text")
        return "text"


async def create_batch_repair_prompt(
    artifacts: List[Artifact],
    verification_results: Dict[str, List[VerificationResult]]
) -> str:
    """Create a repair prompt for multiple artifacts.
    
    Args:
        artifacts: List of artifacts that need repair
        verification_results: Verification results keyed by artifact ID
        
    Returns:
        Comprehensive repair prompt
    """
    analyzer = RepairAnalyzer()
    
    prompt = "Please fix the following code files that have verification failures:\n\n"
    
    for artifact in artifacts:
        results = verification_results.get(str(artifact.id), [])
        if not results:
            continue
        
        # Analyze failures
        suggestions = []
        for result in results:
            if not result.success:
                suggestion = await analyzer.analyze_failure(artifact, result)
                if suggestion:
                    suggestions.append(suggestion)
        
        if suggestions:
            # Add to prompt
            prompt += f"## File: {artifact.name}\n"
            prompt += "Issues:\n"
            for suggestion in suggestions:
                prompt += f"- {suggestion.issue_description}\n"
                prompt += f"  Fix: {suggestion.suggestion}\n"
            prompt += "\n"
    
    prompt += "\nReturn all fixed files with clear separation between them."
    
    return prompt