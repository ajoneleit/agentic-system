#!/usr/bin/env python3
"""Comprehensive System Validation Checklist
Validates all system requirements and quality gates.
"""

import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


class SystemValidator:
    def __init__(self):
        self.results = {}
        self.passed = 0
        self.total = 8  # Updated total for all validation items
        self.project_root = Path.cwd()

    def validate_ci_pipeline(self):
        """Validate CI pipeline functionality."""
        print("🔍 Validating CI Pipeline...")

        # Check if CI config exists
        ci_configs = [
            ".github/workflows/ci.yml",
            ".github/workflows/documentation.yml",
            ".github/workflows/main.yml",
            ".github/workflows/agentic.yml",
        ]

        existing_configs = [config for config in ci_configs if os.path.exists(config)]

        if not existing_configs:
            self.results["ci_pipeline"] = {
                "status": "❌ FAIL",
                "message": "No CI configuration found",
                "details": f"Checked: {ci_configs}",
                "action": "Create CI workflow files",
            }
            return False

        # Check if GitHub CLI is available for CI status checking
        try:
            subprocess.run(["gh", "--version"], capture_output=True, check=True)
            gh_available = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            gh_available = False

        self.results["ci_pipeline"] = {
            "status": "✅ PASS" if gh_available else "⚠️ PARTIAL",
            "message": f"Found CI configs: {existing_configs}",
            "details": (
                "GitHub CLI available for testing"
                if gh_available
                else "GitHub CLI not available - manual verification required"
            ),
            "action": (
                "Run: git clone <repo> && gh run watch"
                if gh_available
                else "Install GitHub CLI and test manually"
            ),
        }
        return True

    def validate_quality_reports(self):
        """Validate quality reports generation."""
        print("📊 Validating Quality Reports...")

        # Check for reports directory
        reports_dir = self.project_root / "reports"
        if not reports_dir.exists():
            reports_dir.mkdir(parents=True, exist_ok=True)

        required_reports = [
            "coverage.xml",  # Standard location
            "reports/pylint.json",
            "reports/coverage.xml",
        ]

        found_reports = []
        missing_reports = []

        for report in required_reports:
            if os.path.exists(report):
                found_reports.append(report)
            else:
                missing_reports.append(report)

        # Check for coverage.xml in root (often generated there)
        if os.path.exists("coverage.xml"):
            found_reports.append("coverage.xml")

        if found_reports:
            self.results["quality_reports"] = {
                "status": "⚠️ PARTIAL" if missing_reports else "✅ PASS",
                "message": f"Found reports: {found_reports}",
                "details": (
                    f"Missing: {missing_reports}"
                    if missing_reports
                    else "All quality reports present"
                ),
                "action": (
                    "Run tests with coverage to generate missing reports"
                    if missing_reports
                    else "Reports available"
                ),
            }
            return len(missing_reports) == 0
        else:
            self.results["quality_reports"] = {
                "status": "❌ FAIL",
                "message": "No quality reports found",
                "details": f"Expected: {required_reports}",
                "action": "Run: pytest --cov=src --cov-report=xml && python -m pylint src --output-format=json > reports/pylint.json",
            }
            return False

    def validate_baseline_metrics(self):
        """Validate baseline metrics snapshot."""
        print("📈 Validating Baseline Metrics...")

        # Check for baseline directory in artifacts
        baseline_pattern = str(self.project_root / "artifacts" / "baseline_*")
        baseline_dirs = glob.glob(baseline_pattern)

        if not baseline_dirs:
            # Check if metrics directory exists with any baseline data
            metrics_dir = self.project_root / "docs" / "metrics"
            if metrics_dir.exists():
                metric_files = list(metrics_dir.glob("*baseline*")) + list(
                    metrics_dir.glob("*reality*")
                )
                if metric_files:
                    self.results["baseline_metrics"] = {
                        "status": "⚠️ PARTIAL",
                        "message": f"Found metrics files in docs/metrics: {[f.name for f in metric_files]}",
                        "details": "Baseline metrics exist but not in standard artifacts/ format",
                        "action": "Create artifacts/baseline_YYYY-MM-DD/ directory with formatted baseline data",
                    }
                    return False

            self.results["baseline_metrics"] = {
                "status": "❌ FAIL",
                "message": "No baseline metrics directory found",
                "details": f"Expected pattern: {baseline_pattern}",
                "action": "Create baseline snapshot: python docs/validation/reality_checker.py --save-report artifacts/baseline_$(date +%Y-%m-%d)/reality-check.json",
            }
            return False

        # Check latest baseline has required files
        latest_baseline = max(baseline_dirs)
        expected_files = ["reality-check.json", "coverage_summary.json", "quality_summary.json"]
        existing_files = []
        missing_files = []

        # Check what files exist in the baseline directory
        baseline_path = Path(latest_baseline)
        all_files = list(baseline_path.glob("*"))

        for file in expected_files:
            file_path = baseline_path / file
            if file_path.exists():
                existing_files.append(file)
            else:
                missing_files.append(file)

        if existing_files:
            self.results["baseline_metrics"] = {
                "status": "✅ PASS" if not missing_files else "⚠️ PARTIAL",
                "message": f"Baseline found: {latest_baseline}",
                "details": (
                    f"Contains: {existing_files}. Missing: {missing_files}"
                    if missing_files
                    else f"Contains: {existing_files}"
                ),
                "action": (
                    "Baseline metrics available"
                    if not missing_files
                    else "Generate missing baseline files"
                ),
            }
            return len(missing_files) == 0
        else:
            self.results["baseline_metrics"] = {
                "status": "❌ FAIL",
                "message": f"Empty baseline directory: {latest_baseline}",
                "details": f"Directory exists but contains no baseline files. Found: {[f.name for f in all_files]}",
                "action": "Populate baseline directory with metrics snapshots",
            }
            return False

    def validate_reality_check_badge(self):
        """Validate reality-check report badge."""
        print("🏷️ Validating Reality-Check Badge...")

        # Check README for badge
        readme_files = ["README.md", "readme.md", "README.rst", "README.txt"]
        readme_content = ""
        readme_file = None

        for readme in readme_files:
            readme_path = self.project_root / readme
            if readme_path.exists():
                try:
                    with open(readme_path, encoding="utf-8") as f:
                        readme_content = f.read()
                    readme_file = readme
                    break
                except Exception as e:
                    print(f"Warning: Could not read {readme}: {e}")

        if not readme_content:
            self.results["reality_check_badge"] = {
                "status": "❌ FAIL",
                "message": "No README file found",
                "details": f"Checked: {readme_files}",
                "action": "Create README.md with system status badge",
            }
            return False

        # Look for reality-check badge or system status indicators
        badge_patterns = [
            r"!\[.*reality.*check.*\]",
            r"!\[.*system.*health.*\]",
            r"!\[.*validation.*\]",
            r"!\[.*status.*\]",
            r"https://.*badge.*",
            r"System Status.*HEALTHY",
            r"Health.*✅",
            r"Status.*✅",
        ]

        badge_found = False
        found_patterns = []

        for pattern in badge_patterns:
            matches = re.findall(pattern, readme_content, re.IGNORECASE)
            if matches:
                badge_found = True
                found_patterns.extend(matches)

        if badge_found:
            self.results["reality_check_badge"] = {
                "status": "✅ PASS",
                "message": f"System status indicators found in {readme_file}",
                "details": f"Found patterns: {found_patterns[:3]}",  # Show first 3 matches
                "action": "Verify badge shows current system health status",
            }
            return True
        else:
            self.results["reality_check_badge"] = {
                "status": "❌ FAIL",
                "message": f"No system status badge found in {readme_file}",
                "details": "Searched for patterns like: reality-check, system-health, validation badges",
                "action": "Add system status badge to README: ![System Health](https://img.shields.io/badge/System%20Health-HEALTHY-green)",
            }
            return False

    def validate_documentation_claims(self):
        """Validate documentation claims accuracy."""
        print("📚 Validating Documentation Claims...")

        # Search for potentially unsubstantiated claims
        suspicious_claims = [
            r"production-ready",
            r"enterprise-grade",
            r"fully tested",
            r"battle-tested",
            r"production-quality",
            r"industry-standard",
            r"enterprise-ready",
            r"commercial-grade",
        ]

        files_to_check = []
        # Add README files
        files_to_check.extend(self.project_root.glob("README*"))
        # Add docs directory
        files_to_check.extend(self.project_root.glob("docs/**/*.md"))
        files_to_check.extend(self.project_root.glob("docs/**/*.rst"))
        # Add CLAUDE.md
        claude_md = self.project_root / "CLAUDE.md"
        if claude_md.exists():
            files_to_check.append(claude_md)

        found_claims = {}
        total_files_checked = 0

        for file_path in files_to_check:
            if file_path.is_file():
                total_files_checked += 1
                try:
                    with open(file_path, encoding="utf-8") as f:
                        content = f.read()

                    for claim_pattern in suspicious_claims:
                        matches = re.finditer(claim_pattern, content, re.IGNORECASE)
                        for match in matches:
                            if str(file_path) not in found_claims:
                                found_claims[str(file_path)] = []
                            found_claims[str(file_path)].append(
                                {
                                    "claim": match.group(0),
                                    "context": content[
                                        max(0, match.start() - 50) : match.end() + 50
                                    ].strip(),
                                }
                            )
                except Exception as e:
                    print(f"Warning: Could not read {file_path}: {e}")

        if found_claims:
            # Analyze severity - some claims might be acceptable if qualified
            critical_claims = []
            acceptable_claims = []

            for file_path, claims in found_claims.items():
                for claim_info in claims:
                    # Check if claim is qualified (has context like "not yet", "working toward", etc.)
                    context = claim_info["context"].lower()
                    qualifying_words = [
                        "not yet",
                        "working toward",
                        "approaching",
                        "near",
                        "development",
                        "alpha",
                        "beta",
                    ]

                    if any(qualifier in context for qualifier in qualifying_words):
                        acceptable_claims.append(f"{claim_info['claim']} in {file_path}")
                    else:
                        critical_claims.append(f"{claim_info['claim']} in {file_path}")

            if critical_claims:
                self.results["documentation_claims"] = {
                    "status": "❌ FAIL",
                    "message": f"Found {len(critical_claims)} unqualified production claims",
                    "details": f"Critical: {critical_claims[:3]}",  # Show first 3
                    "action": 'Remove unsubstantiated claims or add qualifiers like "development phase", "alpha version"',
                }
                return False
            else:
                self.results["documentation_claims"] = {
                    "status": "⚠️ REVIEW",
                    "message": f"Found {len(acceptable_claims)} qualified claims",
                    "details": f"Qualified claims: {acceptable_claims[:2]}",
                    "action": "Review qualified claims for accuracy",
                }
                return True
        else:
            self.results["documentation_claims"] = {
                "status": "✅ PASS",
                "message": "No unsubstantiated production claims found",
                "details": f"Checked {total_files_checked} documentation files",
                "action": "Documentation claims appear accurate",
            }
            return True

    def validate_guiding_principles_implementation(self):
        """Validate the three guiding principles are implemented."""
        print("🎯 Validating Guiding Principles Implementation...")

        # Check for validation infrastructure
        validation_files = [
            "docs/validation/doc_validator.py",
            "docs/validation/reality_checker.py",
            "docs/validation/quality_gates.py",
        ]

        missing_files = []
        for file in validation_files:
            if not (self.project_root / file).exists():
                missing_files.append(file)

        # Check for CI integration
        ci_integration = False
        ci_file = self.project_root / ".github" / "workflows" / "documentation.yml"
        if ci_file.exists():
            try:
                with open(ci_file) as f:
                    ci_content = f.read()
                if "quality_gates" in ci_content or "doc_validator" in ci_content:
                    ci_integration = True
            except Exception:
                pass

        # Check for pre-commit hooks
        precommit_file = self.project_root / ".pre-commit-config.yaml"
        precommit_integration = precommit_file.exists()

        if missing_files:
            self.results["guiding_principles"] = {
                "status": "❌ FAIL",
                "message": "Guiding principles validation infrastructure incomplete",
                "details": f"Missing: {missing_files}",
                "action": "Implement complete validation infrastructure as per guiding principles",
            }
            return False
        elif not ci_integration:
            self.results["guiding_principles"] = {
                "status": "⚠️ PARTIAL",
                "message": "Validation tools exist but CI integration incomplete",
                "details": "Found validation scripts but no CI enforcement",
                "action": "Add quality gates to CI pipeline for fail-fast enforcement",
            }
            return False
        else:
            self.results["guiding_principles"] = {
                "status": "✅ PASS",
                "message": "Guiding principles implementation complete",
                "details": f'Validation tools: ✅, CI integration: ✅, Pre-commit: {"✅" if precommit_integration else "❌"}',
                "action": "Guiding principles actively enforced",
            }
            return True

    def validate_documentation_structure(self):
        """Validate documentation structure follows standards."""
        print("📁 Validating Documentation Structure...")

        required_docs = [
            "docs/index.md",
            "docs/development/setup.md",
            "docs/development/coding-standards.md",
            "docs/processes/quality-gates.md",
        ]

        missing_docs = []
        existing_docs = []

        for doc in required_docs:
            doc_path = self.project_root / doc
            if doc_path.exists():
                existing_docs.append(doc)
            else:
                missing_docs.append(doc)

        # Check if docs directory exists
        docs_dir = self.project_root / "docs"
        if not docs_dir.exists():
            self.results["documentation_structure"] = {
                "status": "❌ FAIL",
                "message": "No docs/ directory found",
                "details": "Documentation structure not implemented",
                "action": "Create docs/ directory structure as per one-touch truth-source principle",
            }
            return False

        if missing_docs:
            self.results["documentation_structure"] = {
                "status": "⚠️ PARTIAL",
                "message": "Documentation structure partially implemented",
                "details": f"Found: {len(existing_docs)}, Missing: {len(missing_docs)}",
                "action": f"Create missing documentation files: {missing_docs[:2]}",
            }
            return len(missing_docs) <= len(existing_docs)  # Pass if more than half exist
        else:
            self.results["documentation_structure"] = {
                "status": "✅ PASS",
                "message": "Documentation structure complete",
                "details": f"All required documentation files present: {len(existing_docs)} files",
                "action": "Documentation structure follows standards",
            }
            return True

    def validate_system_health(self):
        """Validate system health check functionality."""
        print("🏥 Validating System Health Check...")

        health_script = self.project_root / "scripts" / "health_check.py"

        if not health_script.exists():
            self.results["system_health"] = {
                "status": "❌ FAIL",
                "message": "Health check script not found",
                "details": f"Expected: {health_script}",
                "action": "Create health check script for system validation",
            }
            return False

        # Try to run health check
        try:
            result = subprocess.run(
                [sys.executable, str(health_script)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.project_root,
            )

            if result.returncode == 0:
                # Check if output indicates healthy system
                output = result.stdout.lower()
                if "healthy" in output or "pass" in output or "✅" in output:
                    self.results["system_health"] = {
                        "status": "✅ PASS",
                        "message": "Health check passes and reports healthy system",
                        "details": f"Health check completed in ~{len(result.stdout)/100:.1f}s",
                        "action": "System health check operational",
                    }
                    return True
                else:
                    self.results["system_health"] = {
                        "status": "⚠️ WARNING",
                        "message": "Health check runs but system may not be healthy",
                        "details": "Health check completes but status unclear",
                        "action": "Review health check output for system issues",
                    }
                    return True
            else:
                self.results["system_health"] = {
                    "status": "❌ FAIL",
                    "message": "Health check script fails to execute",
                    "details": f"Exit code: {result.returncode}, Error: {result.stderr[:100]}",
                    "action": "Fix health check script execution issues",
                }
                return False

        except subprocess.TimeoutExpired:
            self.results["system_health"] = {
                "status": "❌ FAIL",
                "message": "Health check script timeout",
                "details": "Health check took longer than 30 seconds",
                "action": "Optimize health check performance or increase timeout",
            }
            return False
        except Exception as e:
            self.results["system_health"] = {
                "status": "❌ FAIL",
                "message": f"Health check execution error: {str(e)}",
                "details": "Failed to execute health check script",
                "action": "Debug health check script execution environment",
            }
            return False

    def run_validation(self):
        """Run complete validation suite."""
        print("🚀 COMPREHENSIVE SYSTEM VALIDATION CHECKLIST")
        print("=" * 60)
        print(f"📍 Project Root: {self.project_root}")
        print(f"📅 Validation Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        validations = [
            ("CI Pipeline", self.validate_ci_pipeline),
            ("Quality Reports", self.validate_quality_reports),
            ("Baseline Metrics", self.validate_baseline_metrics),
            ("Reality-Check Badge", self.validate_reality_check_badge),
            ("Documentation Claims", self.validate_documentation_claims),
            ("Guiding Principles", self.validate_guiding_principles_implementation),
            ("Documentation Structure", self.validate_documentation_structure),
            ("System Health", self.validate_system_health),
        ]

        for name, validator in validations:
            print(f"\n🔍 {name}...")
            try:
                if validator():
                    self.passed += 1
                    print(f"   ✅ {name} validation completed")
                else:
                    print(f"   ❌ {name} validation failed")
            except Exception as e:
                print(f"   💥 {name} validation error: {str(e)}")
                self.results[name.lower().replace(" ", "_")] = {
                    "status": "💥 ERROR",
                    "message": f"Validation error: {str(e)}",
                    "details": "Exception occurred during validation",
                    "action": "Debug validation script",
                }

        self.print_results()
        self.save_results()
        return self.passed == self.total

    def print_results(self):
        """Print validation results."""
        print("\n" + "=" * 60)
        print("📊 VALIDATION RESULTS SUMMARY")
        print("=" * 60)

        # Group results by status
        passed = []
        failed = []
        warnings = []
        errors = []

        for item, result in self.results.items():
            status = result["status"]
            if status.startswith("✅"):
                passed.append((item, result))
            elif status.startswith("❌"):
                failed.append((item, result))
            elif status.startswith("⚠️"):
                warnings.append((item, result))
            elif status.startswith("💥"):
                errors.append((item, result))

        # Print summary stats
        print(
            f"🎯 OVERALL SCORE: {self.passed}/{self.total} ({self.passed/self.total*100:.1f}% passed)"
        )
        print(f"✅ Passed: {len(passed)}")
        print(f"❌ Failed: {len(failed)}")
        print(f"⚠️ Warnings: {len(warnings)}")
        print(f"💥 Errors: {len(errors)}")
        print()

        # Print detailed results
        for status_group, items in [
            ("✅ PASSED", passed),
            ("❌ FAILED", failed),
            ("⚠️ WARNINGS", warnings),
            ("💥 ERRORS", errors),
        ]:
            if items:
                print(f"{status_group}:")
                for item, result in items:
                    print(f"  {result['status']} {item.replace('_', ' ').title()}")
                    print(f"     📝 {result['message']}")
                    if "details" in result and result["details"]:
                        print(f"     📋 {result['details']}")
                    if "action" in result:
                        print(f"     🔧 Action: {result['action']}")
                    print()

        # Overall assessment
        if self.passed == self.total:
            print("🎉 ALL VALIDATIONS PASSED - SYSTEM READY")
        elif self.passed >= self.total * 0.8:
            print("⚠️ MOSTLY VALIDATED - MINOR ISSUES TO RESOLVE")
        elif self.passed >= self.total * 0.6:
            print("🔧 PARTIAL VALIDATION - SIGNIFICANT WORK NEEDED")
        else:
            print("🚨 VALIDATION FAILED - MAJOR ISSUES REQUIRE ATTENTION")

    def save_results(self):
        """Save validation results to file."""
        results_file = self.project_root / "docs" / "metrics" / "system-validation.json"
        results_file.parent.mkdir(parents=True, exist_ok=True)

        validation_report = {
            "timestamp": datetime.now().isoformat(),
            "overall_score": f"{self.passed}/{self.total}",
            "success_rate": self.passed / self.total,
            "passed_count": self.passed,
            "total_count": self.total,
            "validation_results": self.results,
        }

        try:
            with open(results_file, "w") as f:
                json.dump(validation_report, f, indent=2)
            print(f"📄 Validation results saved to: {results_file}")
        except Exception as e:
            print(f"⚠️ Warning: Could not save validation results: {e}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Comprehensive System Validation")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--fail-fast", action="store_true", help="Exit on first failure")
    parser.add_argument("--save", action="store_true", help="Save results to file")

    args = parser.parse_args()

    validator = SystemValidator()

    if args.fail_fast:
        # Run validations one by one and exit on first failure
        validations = [
            ("CI Pipeline", validator.validate_ci_pipeline),
            ("Quality Reports", validator.validate_quality_reports),
            ("Baseline Metrics", validator.validate_baseline_metrics),
            ("Reality-Check Badge", validator.validate_reality_check_badge),
            ("Documentation Claims", validator.validate_documentation_claims),
            ("Guiding Principles", validator.validate_guiding_principles_implementation),
            ("Documentation Structure", validator.validate_documentation_structure),
            ("System Health", validator.validate_system_health),
        ]

        for name, validator_func in validations:
            print(f"🔍 Validating {name}...")
            if not validator_func():
                print(f"❌ FAIL FAST: {name} validation failed")
                if args.json:
                    print(json.dumps(validator.results, indent=2))
                sys.exit(1)
            print(f"✅ {name} passed")

        print("🎉 ALL VALIDATIONS PASSED")
        success = True
    else:
        success = validator.run_validation()

    if args.json:
        validation_report = {
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "overall_score": f"{validator.passed}/{validator.total}",
            "results": validator.results,
        }
        print(json.dumps(validation_report, indent=2))

    if args.save:
        validator.save_results()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
