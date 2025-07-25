#!/usr/bin/env python3
"""Metrics Validator - Validates performance and quality metrics claims.

This module ensures all metrics claims in documentation are backed by actual
measurements and maintains metric accuracy over time.
"""

import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class MetricClaim:
    """A performance or quality claim found in documentation."""

    file_path: str
    line_number: int
    claim_text: str
    metric_type: str  # 'performance', 'coverage', 'size', 'count'
    claimed_value: str
    unit: Optional[str] = None
    context: Optional[str] = None


@dataclass
class MetricMeasurement:
    """An actual measurement of a metric."""

    metric_name: str
    measured_value: float
    unit: str
    timestamp: datetime
    measurement_method: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricValidation:
    """Result of validating a metric claim against measurements."""

    claim: MetricClaim
    measurement: Optional[MetricMeasurement]
    is_valid: bool
    discrepancy: Optional[float]
    message: str


class MetricsValidator:
    """Validates metrics claims against actual measurements."""

    def __init__(self, project_root: Path = None):
        """Initialize metrics validator."""
        self.project_root = project_root or Path.cwd()
        self.docs_root = self.project_root / "docs"
        self.metrics_cache: dict[str, list[MetricMeasurement]] = {}

    def extract_metric_claims(self) -> list[MetricClaim]:
        """Extract all metric claims from documentation."""
        claims = []

        # Find all markdown files
        doc_files = list(self.docs_root.rglob("*.md"))

        # Patterns for different types of metric claims
        patterns = {
            "performance": [
                r"(\d+\.?\d*)\s*%\s+(improvement|faster|reduction)",
                r"<\s*(\d+\.?\d*)\s+(seconds?|minutes?|ms)",
                r"(\d+\.?\d*x)\s+(faster|throughput|speedup)",
                r"(\d+\.?\d*)\s+(MB|GB|KB)\s+(memory|RAM|usage)",
            ],
            "coverage": [
                r"(\d+\.?\d*)%\s+(coverage|test coverage)",
                r"(\d+)\s+(test files?|tests?)",
            ],
            "size": [
                r"(\d+,?\d*)\s+(lines? of code|LOC)",
                r"(\d+\.?\d*)\s+(MB|GB|KB)\s+(size|storage)",
            ],
            "count": [
                r"(\d+)\s+(components?|modules?|agents?|files?)",
            ],
        }

        for doc_file in doc_files:
            try:
                content = doc_file.read_text(encoding="utf-8")
                lines = content.split("\n")

                for line_num, line in enumerate(lines, 1):
                    for metric_type, type_patterns in patterns.items():
                        for pattern in type_patterns:
                            matches = re.finditer(pattern, line, re.IGNORECASE)
                            for match in matches:
                                claims.append(
                                    MetricClaim(
                                        file_path=str(doc_file.relative_to(self.project_root)),
                                        line_number=line_num,
                                        claim_text=match.group(0),
                                        metric_type=metric_type,
                                        claimed_value=match.group(1),
                                        unit=match.group(2) if len(match.groups()) > 1 else None,
                                        context=line.strip(),
                                    )
                                )

            except Exception as e:
                print(f"Warning: Failed to process {doc_file}: {e}")

        return claims

    def measure_performance_metrics(self) -> list[MetricMeasurement]:
        """Measure actual performance metrics."""
        measurements = []

        # Measure health check performance
        try:
            start_time = time.time()
            result = subprocess.run(
                [sys.executable, "scripts/health_check.py"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=30,
            )
            elapsed_time = time.time() - start_time

            if result.returncode == 0:
                measurements.append(
                    MetricMeasurement(
                        metric_name="health_check_time",
                        measured_value=elapsed_time,
                        unit="seconds",
                        timestamp=datetime.now(),
                        measurement_method="subprocess_execution",
                        details={"return_code": result.returncode},
                    )
                )
        except Exception as e:
            print(f"Warning: Failed to measure health check performance: {e}")

        # Measure import time
        try:
            start_time = time.time()
            result = subprocess.run(
                [sys.executable, "-c", "from src.agents.meta_agent import MetaAgent"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
            )
            elapsed_time = time.time() - start_time

            if result.returncode == 0:
                measurements.append(
                    MetricMeasurement(
                        metric_name="meta_agent_import_time",
                        measured_value=elapsed_time,
                        unit="seconds",
                        timestamp=datetime.now(),
                        measurement_method="import_timing",
                        details={"return_code": result.returncode},
                    )
                )
        except Exception as e:
            print(f"Warning: Failed to measure import time: {e}")

        return measurements

    def measure_code_metrics(self) -> list[MetricMeasurement]:
        """Measure code size and structure metrics."""
        measurements = []

        # Count lines of code
        try:
            src_files = list(self.project_root.glob("src/**/*.py"))
            total_lines = 0

            for src_file in src_files:
                try:
                    lines = len(src_file.read_text(encoding="utf-8").splitlines())
                    total_lines += lines
                except Exception:
                    continue  # Skip files that can't be read

            measurements.append(
                MetricMeasurement(
                    metric_name="lines_of_code",
                    measured_value=float(total_lines),
                    unit="lines",
                    timestamp=datetime.now(),
                    measurement_method="file_counting",
                    details={"files_counted": len(src_files)},
                )
            )
        except Exception as e:
            print(f"Warning: Failed to count lines of code: {e}")

        # Count test files
        try:
            test_files = list(self.project_root.glob("tests/**/*.py"))
            test_files += list(self.project_root.glob("test_*.py"))

            measurements.append(
                MetricMeasurement(
                    metric_name="test_file_count",
                    measured_value=float(len(test_files)),
                    unit="files",
                    timestamp=datetime.now(),
                    measurement_method="file_counting",
                    details={"test_directories": ["tests", "."]},
                )
            )
        except Exception as e:
            print(f"Warning: Failed to count test files: {e}")

        return measurements

    def measure_coverage_metrics(self) -> list[MetricMeasurement]:
        """Measure test coverage metrics."""
        measurements = []

        # Check for coverage data
        coverage_file = self.project_root / "coverage.xml"
        if coverage_file.exists():
            try:
                # Parse coverage XML for actual coverage percentage
                import xml.etree.ElementTree as ET

                tree = ET.parse(coverage_file)
                root = tree.getroot()

                # Look for coverage attribute
                coverage_elem = root.find(".//coverage")
                if coverage_elem is not None and "line-rate" in coverage_elem.attrib:
                    coverage_rate = float(coverage_elem.attrib["line-rate"])
                    coverage_percent = coverage_rate * 100

                    measurements.append(
                        MetricMeasurement(
                            metric_name="test_coverage",
                            measured_value=coverage_percent,
                            unit="percent",
                            timestamp=datetime.now(),
                            measurement_method="coverage_xml_parsing",
                            details={"coverage_file": str(coverage_file)},
                        )
                    )
            except Exception as e:
                print(f"Warning: Failed to parse coverage data: {e}")

        return measurements

    def validate_claims(
        self, claims: list[MetricClaim], measurements: list[MetricMeasurement]
    ) -> list[MetricValidation]:
        """Validate metric claims against measurements."""
        validations = []

        # Create measurement lookup
        measurement_lookup = {}
        for measurement in measurements:
            measurement_lookup[measurement.metric_name] = measurement

        for claim in claims:
            validation = self._validate_single_claim(claim, measurement_lookup)
            validations.append(validation)

        return validations

    def _validate_single_claim(
        self, claim: MetricClaim, measurement_lookup: dict[str, MetricMeasurement]
    ) -> MetricValidation:
        """Validate a single metric claim."""
        # Map claim to measurement
        measurement_key = self._map_claim_to_measurement(claim)
        measurement = measurement_lookup.get(measurement_key)

        if measurement is None:
            return MetricValidation(
                claim=claim,
                measurement=None,
                is_valid=False,
                discrepancy=None,
                message=f"No measurement available for claim: {claim.claim_text}",
            )

        # Parse claimed value
        try:
            claimed_numeric = self._parse_numeric_value(claim.claimed_value)
        except ValueError:
            return MetricValidation(
                claim=claim,
                measurement=measurement,
                is_valid=False,
                discrepancy=None,
                message=f"Cannot parse claimed value: {claim.claimed_value}",
            )

        # Compare values
        measured_value = measurement.measured_value

        # Calculate discrepancy (percentage difference)
        if claimed_numeric != 0:
            discrepancy = abs((measured_value - claimed_numeric) / claimed_numeric) * 100
        else:
            discrepancy = abs(measured_value) * 100

        # Determine validation result based on claim type
        tolerance = self._get_tolerance_for_claim_type(claim.metric_type)
        is_valid = discrepancy <= tolerance

        if is_valid:
            message = f"Claim validated: {claim.claimed_value} vs measured {measured_value:.2f}"
        else:
            message = f"Claim invalid: {claim.claimed_value} vs measured {measured_value:.2f} (discrepancy: {discrepancy:.1f}%)"

        return MetricValidation(
            claim=claim,
            measurement=measurement,
            is_valid=is_valid,
            discrepancy=discrepancy,
            message=message,
        )

    def _map_claim_to_measurement(self, claim: MetricClaim) -> Optional[str]:
        """Map a claim to a measurement key."""
        claim_text_lower = claim.claim_text.lower()

        # Performance mappings
        if "health check" in claim.context.lower() and "seconds" in claim_text_lower:
            return "health_check_time"
        if "import" in claim.context.lower() and "seconds" in claim_text_lower:
            return "meta_agent_import_time"

        # Coverage mappings
        if "coverage" in claim_text_lower:
            return "test_coverage"
        if "test files" in claim_text_lower or "test file" in claim_text_lower:
            return "test_file_count"

        # Size mappings
        if "lines of code" in claim_text_lower or "loc" in claim_text_lower:
            return "lines_of_code"

        return None

    def _parse_numeric_value(self, value_str: str) -> float:
        """Parse numeric value from string."""
        # Remove common non-numeric characters
        cleaned = re.sub(r"[,<>~]", "", value_str.strip())

        # Handle 'x' suffix (like "22.84x")
        if cleaned.endswith("x"):
            cleaned = cleaned[:-1]

        return float(cleaned)

    def _get_tolerance_for_claim_type(self, metric_type: str) -> float:
        """Get tolerance percentage for different metric types."""
        tolerances = {
            "performance": 20.0,  # 20% tolerance for performance claims
            "coverage": 5.0,  # 5% tolerance for coverage claims
            "size": 10.0,  # 10% tolerance for size claims
            "count": 0.0,  # 0% tolerance for count claims (should be exact)
        }
        return tolerances.get(metric_type, 15.0)

    def generate_metrics_report(self, validations: list[MetricValidation]) -> dict[str, Any]:
        """Generate comprehensive metrics validation report."""
        total_claims = len(validations)
        valid_claims = sum(1 for v in validations if v.is_valid)
        invalid_claims = total_claims - valid_claims

        # Group by metric type
        claims_by_type = {}
        for validation in validations:
            metric_type = validation.claim.metric_type
            if metric_type not in claims_by_type:
                claims_by_type[metric_type] = {"total": 0, "valid": 0}
            claims_by_type[metric_type]["total"] += 1
            if validation.is_valid:
                claims_by_type[metric_type]["valid"] += 1

        # Find worst discrepancies
        invalid_validations = [
            v for v in validations if not v.is_valid and v.discrepancy is not None
        ]
        worst_discrepancies = sorted(
            invalid_validations, key=lambda v: v.discrepancy or 0, reverse=True
        )[:5]

        return {
            "summary": {
                "total_claims": total_claims,
                "valid_claims": valid_claims,
                "invalid_claims": invalid_claims,
                "validation_rate": valid_claims / total_claims if total_claims > 0 else 1.0,
                "timestamp": datetime.now().isoformat(),
            },
            "by_metric_type": {
                metric_type: {
                    "total": stats["total"],
                    "valid": stats["valid"],
                    "success_rate": stats["valid"] / stats["total"] if stats["total"] > 0 else 1.0,
                }
                for metric_type, stats in claims_by_type.items()
            },
            "worst_discrepancies": [
                {
                    "claim_text": v.claim.claim_text,
                    "file": v.claim.file_path,
                    "line": v.claim.line_number,
                    "discrepancy_percent": v.discrepancy,
                    "message": v.message,
                }
                for v in worst_discrepancies
            ],
            "all_validations": [
                {
                    "claim_text": v.claim.claim_text,
                    "file": v.claim.file_path,
                    "line": v.claim.line_number,
                    "metric_type": v.claim.metric_type,
                    "is_valid": v.is_valid,
                    "discrepancy_percent": v.discrepancy,
                    "message": v.message,
                    "measured_value": v.measurement.measured_value if v.measurement else None,
                    "measurement_unit": v.measurement.unit if v.measurement else None,
                }
                for v in validations
            ],
        }

    def save_metrics_history(self, measurements: list[MetricMeasurement]) -> None:
        """Save measurements to history file."""
        history_file = self.project_root / "docs" / "metrics" / "metrics-history.json"
        history_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing history
        history = []
        if history_file.exists():
            try:
                with open(history_file) as f:
                    history = json.load(f)
            except Exception:
                history = []

        # Add new measurements
        for measurement in measurements:
            history.append(
                {
                    "metric_name": measurement.metric_name,
                    "measured_value": measurement.measured_value,
                    "unit": measurement.unit,
                    "timestamp": measurement.timestamp.isoformat(),
                    "measurement_method": measurement.measurement_method,
                    "details": measurement.details,
                }
            )

        # Keep only last 100 measurements per metric
        metric_counts = {}
        filtered_history = []

        # Sort by timestamp (newest first)
        history.sort(key=lambda x: x["timestamp"], reverse=True)

        for entry in history:
            metric_name = entry["metric_name"]
            if metric_name not in metric_counts:
                metric_counts[metric_name] = 0

            if metric_counts[metric_name] < 100:
                filtered_history.append(entry)
                metric_counts[metric_name] += 1

        # Save updated history
        with open(history_file, "w") as f:
            json.dump(filtered_history, f, indent=2)


def main():
    """Main entry point for metrics validation."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate metrics claims against measurements")
    parser.add_argument(
        "--extract-claims", action="store_true", help="Extract metric claims from documentation"
    )
    parser.add_argument("--measure-all", action="store_true", help="Measure all available metrics")
    parser.add_argument(
        "--validate-all", action="store_true", help="Validate all claims against measurements"
    )
    parser.add_argument(
        "--generate-report", action="store_true", help="Generate metrics validation report"
    )
    parser.add_argument("--save-history", action="store_true", help="Save measurements to history")
    parser.add_argument(
        "--fail-on-invalid", action="store_true", help="Exit with error on invalid claims"
    )

    args = parser.parse_args()

    validator = MetricsValidator()

    # Extract claims
    if args.extract_claims or args.validate_all or not any(vars(args).values()):
        claims = validator.extract_metric_claims()
        print(f"Extracted {len(claims)} metric claims from documentation")

        if args.extract_claims:
            for claim in claims:
                print(f"  {claim.file_path}:{claim.line_number} - {claim.claim_text}")

    # Measure metrics
    if args.measure_all or args.validate_all or not any(vars(args).values()):
        print("Measuring performance metrics...")
        performance_measurements = validator.measure_performance_metrics()

        print("Measuring code metrics...")
        code_measurements = validator.measure_code_metrics()

        print("Measuring coverage metrics...")
        coverage_measurements = validator.measure_coverage_metrics()

        all_measurements = performance_measurements + code_measurements + coverage_measurements
        print(f"Collected {len(all_measurements)} measurements")

        if args.save_history:
            validator.save_metrics_history(all_measurements)
            print("Measurements saved to history")

    # Validate claims
    if args.validate_all or not any(vars(args).values()):
        validations = validator.validate_claims(claims, all_measurements)

        valid_count = sum(1 for v in validations if v.is_valid)
        invalid_count = len(validations) - valid_count

        print(f"\nValidation Results: {valid_count} valid, {invalid_count} invalid")

        # Show invalid claims
        invalid_validations = [v for v in validations if not v.is_valid]
        if invalid_validations:
            print("\nInvalid Claims:")
            for validation in invalid_validations:
                print(f"  ❌ {validation.claim.file_path}:{validation.claim.line_number}")
                print(f"     {validation.message}")

        if args.generate_report:
            report = validator.generate_metrics_report(validations)
            print("\nMetrics Validation Report:")
            print(json.dumps(report, indent=2))

        if args.fail_on_invalid and invalid_count > 0:
            print(f"\nFAILED: {invalid_count} invalid metric claims found")
            sys.exit(1)


if __name__ == "__main__":
    main()
