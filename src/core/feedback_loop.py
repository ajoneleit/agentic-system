"""Feedback loop system for iterative improvement through Claude CLI.

This module manages the iterative refinement process, evaluating outputs
and determining next actions based on quality scores and task requirements.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from structlog import get_logger

from src.core.interfaces import AgentRole
from src.verification.quality_gates import QualityIssue, QualityResult

logger = get_logger(__name__)


class FeedbackAction(Enum):
    """Actions that can be taken based on feedback."""

    COMPLETE = "complete"  # Task completed successfully
    RETRY = "retry"  # Retry with improvements
    ESCALATE = "escalate"  # Escalate to specialized agent
    REVIEW = "review"  # Needs human review
    CLARIFY = "clarify"  # Needs clarification from user


@dataclass
class FeedbackDecision:
    """Decision made by the feedback loop."""

    action: FeedbackAction
    reason: str
    confidence: float  # 0.0 to 1.0
    target_agent: Optional[AgentRole] = None
    clarification_prompt: Optional[str] = None
    improvement_prompt: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class FeedbackHistory:
    """History of feedback iterations for a task."""

    task_id: UUID
    iterations: list[dict[str, Any]]
    total_attempts: int
    final_score: Optional[float] = None
    completed: bool = False

    def add_iteration(self, quality_result: QualityResult, decision: FeedbackDecision):
        """Add an iteration to the history."""
        self.iterations.append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "quality_score": quality_result.metrics.overall_score,
                "passed": quality_result.passed,
                "issues_count": len(quality_result.issues),
                "action": decision.action.value,
                "reason": decision.reason,
            }
        )
        self.total_attempts += 1


class IssueAnalyzer:
    """Analyzes quality issues to determine appropriate actions."""

    def analyze_issues(self, issues: list[QualityIssue]) -> dict[str, Any]:
        """Analyze issues to identify patterns and severity.

        Args:
            issues: List of quality issues

        Returns:
            Analysis summary

        """
        analysis = {
            "total_issues": len(issues),
            "critical_count": 0,
            "high_count": 0,
            "medium_count": 0,
            "low_count": 0,
            "categories": {},
            "needs_security_expert": False,
            "needs_performance_expert": False,
            "needs_testing_expert": False,
        }

        for issue in issues:
            # Count by severity
            severity_key = f"{issue.severity}_count"
            if severity_key in analysis:
                analysis[severity_key] += 1

            # Count by category
            if issue.category not in analysis["categories"]:
                analysis["categories"][issue.category] = 0
            analysis["categories"][issue.category] += 1

            # Check for specialist needs
            if issue.category == "security" and issue.severity in ["critical", "high"]:
                analysis["needs_security_expert"] = True
            elif issue.category == "performance" and issue.severity in ["critical", "high"]:
                analysis["needs_performance_expert"] = True
            elif issue.category in ["testing", "test_coverage"] and issue.severity == "critical":
                analysis["needs_testing_expert"] = True

        return analysis


class FeedbackLoopManager:
    """Manages iterative improvement through feedback loops."""

    def __init__(
        self,
        max_iterations: int = 3,
        min_improvement_threshold: float = 0.1,
        target_quality_score: float = 0.95,
    ):
        """Initialize feedback loop manager.

        Args:
            max_iterations: Maximum improvement iterations
            min_improvement_threshold: Minimum score improvement to continue
            target_quality_score: Target quality score to achieve

        """
        self.max_iterations = max_iterations
        self.min_improvement_threshold = min_improvement_threshold
        self.target_quality_score = target_quality_score
        self.issue_analyzer = IssueAnalyzer()
        self._feedback_history: dict[UUID, FeedbackHistory] = {}

        logger.info(
            "Feedback loop manager initialized",
            max_iterations=max_iterations,
            target_score=target_quality_score,
        )

    async def evaluate_output(
        self, output: Any, task: dict[str, Any], quality_result: QualityResult
    ) -> FeedbackDecision:
        """Evaluate output and determine next action.

        Args:
            output: The output to evaluate (CLI result or code)
            task: Task information
            quality_result: Quality validation result

        Returns:
            Feedback decision

        """
        task_id = UUID(task.get("id", "00000000-0000-0000-0000-000000000000"))

        # Initialize or get feedback history
        if task_id not in self._feedback_history:
            self._feedback_history[task_id] = FeedbackHistory(
                task_id=task_id, iterations=[], total_attempts=1
            )
        else:
            self._feedback_history[task_id].total_attempts += 1

        history = self._feedback_history[task_id]

        # Check if quality passed
        if (
            quality_result.passed
            and quality_result.metrics.overall_score >= self.target_quality_score
        ):
            history.final_score = quality_result.metrics.overall_score
            history.completed = True

            decision = FeedbackDecision(
                action=FeedbackAction.COMPLETE,
                reason=f"Quality score {quality_result.metrics.overall_score:.2f} meets target",
                confidence=0.95,
            )

            history.add_iteration(quality_result, decision)
            return decision

        # Analyze issues
        issue_analysis = self.issue_analyzer.analyze_issues(quality_result.issues)

        # Check if we've exceeded max iterations
        if history.total_attempts >= self.max_iterations:
            # Determine if human review is needed
            if issue_analysis["critical_count"] > 0:
                decision = FeedbackDecision(
                    action=FeedbackAction.REVIEW,
                    reason=f"Critical issues remain after {self.max_iterations} attempts",
                    confidence=0.8,
                    metadata={"issue_analysis": issue_analysis},
                )
            else:
                decision = FeedbackDecision(
                    action=FeedbackAction.COMPLETE,
                    reason=f"Best effort after {self.max_iterations} attempts",
                    confidence=0.6,
                    metadata={"final_score": quality_result.metrics.overall_score},
                )

            history.add_iteration(quality_result, decision)
            return decision

        # Check if we need specialist help
        if issue_analysis["needs_security_expert"]:
            decision = FeedbackDecision(
                action=FeedbackAction.ESCALATE,
                reason="Critical security issues require specialist",
                confidence=0.9,
                target_agent=AgentRole.TESTING,  # Security specialist
                metadata={"specialist_type": "security"},
            )
            history.add_iteration(quality_result, decision)
            return decision

        # Check improvement rate
        if len(history.iterations) > 0:
            last_score = history.iterations[-1].get("quality_score", 0)
            improvement = quality_result.metrics.overall_score - last_score

            if improvement < self.min_improvement_threshold:
                # Not improving enough, try clarification
                clarification = await self._generate_clarification(
                    task, quality_result, issue_analysis
                )

                decision = FeedbackDecision(
                    action=FeedbackAction.CLARIFY,
                    reason=f"Insufficient improvement ({improvement:.2f})",
                    confidence=0.7,
                    clarification_prompt=clarification,
                )
                history.add_iteration(quality_result, decision)
                return decision

        # Default: retry with improvements
        improvement_prompt = await self._generate_improvement_prompt(
            task, quality_result, issue_analysis
        )

        decision = FeedbackDecision(
            action=FeedbackAction.RETRY,
            reason="Quality issues can be addressed with improvements",
            confidence=0.8,
            improvement_prompt=improvement_prompt,
            metadata={
                "current_score": quality_result.metrics.overall_score,
                "target_score": self.target_quality_score,
                "issues_to_fix": issue_analysis["total_issues"],
            },
        )

        history.add_iteration(quality_result, decision)
        return decision

    async def _generate_clarification(
        self, task: dict[str, Any], quality_result: QualityResult, issue_analysis: dict[str, Any]
    ) -> str:
        """Generate clarification request based on persistent issues.

        Args:
            task: Task information
            quality_result: Quality result
            issue_analysis: Issue analysis

        Returns:
            Clarification prompt

        """
        sections = [
            f"# Clarification Needed: {task.get('name', 'Task')}",
            "",
            "We're having difficulty meeting the quality requirements. Please clarify:",
            "",
        ]

        # Add specific clarification requests based on issues
        if issue_analysis["categories"].get("test_coverage", 0) > 2:
            sections.extend(
                [
                    "## Test Coverage Requirements:",
                    "- What specific scenarios must be tested?",
                    "- Are there edge cases we should consider?",
                    "- What is the expected behavior for error conditions?",
                    "",
                ]
            )

        if issue_analysis["categories"].get("documentation", 0) > 3:
            sections.extend(
                [
                    "## Documentation Requirements:",
                    "- What level of detail is needed in docstrings?",
                    "- Should we include usage examples?",
                    "- Are there specific formatting requirements?",
                    "",
                ]
            )

        if issue_analysis["categories"].get("error_handling", 0) > 0:
            sections.extend(
                [
                    "## Error Handling Requirements:",
                    "- What types of errors should be caught?",
                    "- How should errors be reported?",
                    "- Should we fail fast or attempt recovery?",
                    "",
                ]
            )

        sections.extend(
            [
                "## Current Status:",
                f"- Quality Score: {quality_result.metrics.overall_score:.2f}",
                f"- Outstanding Issues: {issue_analysis['total_issues']}",
                "",
                "Please provide additional guidance to help achieve the quality targets.",
            ]
        )

        return "\n".join(sections)

    async def _generate_improvement_prompt(
        self, task: dict[str, Any], quality_result: QualityResult, issue_analysis: dict[str, Any]
    ) -> str:
        """Generate improvement prompt for retry.

        Args:
            task: Task information
            quality_result: Quality result
            issue_analysis: Issue analysis

        Returns:
            Improvement prompt

        """
        sections = [
            f"# Improvement Required: {task.get('name', 'Task')}",
            "",
            f"Current quality score: {quality_result.metrics.overall_score:.2f} (target: {self.target_quality_score})",
            "",
            "Please address the following to improve quality:",
            "",
        ]

        # Prioritize critical and high severity issues
        critical_issues = [i for i in quality_result.issues if i.severity == "critical"]
        high_issues = [i for i in quality_result.issues if i.severity == "high"]

        if critical_issues:
            sections.append("## CRITICAL Issues (must fix):")
            for issue in critical_issues[:5]:  # Top 5
                sections.append(f"- {issue.description}")
                if issue.suggestion:
                    sections.append(f"  → {issue.suggestion}")
            sections.append("")

        if high_issues:
            sections.append("## High Priority Issues:")
            for issue in high_issues[:3]:  # Top 3
                sections.append(f"- {issue.description}")
                if issue.suggestion:
                    sections.append(f"  → {issue.suggestion}")
            sections.append("")

        # Add specific improvement strategies
        sections.append("## Improvement Strategies:")

        if quality_result.metrics.test_coverage_estimate < 0.8:
            sections.append(
                "- Add comprehensive test cases covering edge cases and error conditions"
            )

        if quality_result.metrics.security_score < 0.95:
            sections.append("- Review and fix all security vulnerabilities")
            sections.append("- Use secure coding practices (input validation, safe functions)")

        if quality_result.metrics.documentation_score < 0.8:
            sections.append("- Add detailed docstrings to all functions and classes")
            sections.append("- Include parameter descriptions and return value documentation")

        if quality_result.metrics.complexity_score < 0.7:
            sections.append("- Refactor complex functions into smaller, focused functions")
            sections.append("- Reduce nesting levels and cyclomatic complexity")

        sections.extend(
            [
                "",
                "Focus on fixing critical issues first, then address other quality metrics.",
                "Ensure all original requirements are still met after improvements.",
            ]
        )

        return "\n".join(sections)

    def get_feedback_history(self, task_id: UUID) -> Optional[FeedbackHistory]:
        """Get feedback history for a task.

        Args:
            task_id: Task ID

        Returns:
            Feedback history if available

        """
        return self._feedback_history.get(task_id)

    def get_statistics(self) -> dict[str, Any]:
        """Get feedback loop statistics.

        Returns:
            Statistics dictionary

        """
        completed_tasks = [h for h in self._feedback_history.values() if h.completed]

        return {
            "total_tasks": len(self._feedback_history),
            "completed_tasks": len(completed_tasks),
            "average_iterations": (
                sum(h.total_attempts for h in self._feedback_history.values())
                / len(self._feedback_history)
                if self._feedback_history
                else 0
            ),
            "average_final_score": (
                sum(h.final_score for h in completed_tasks if h.final_score) / len(completed_tasks)
                if completed_tasks
                else 0
            ),
            "success_rate": (
                len(completed_tasks) / len(self._feedback_history) if self._feedback_history else 0
            ),
        }
