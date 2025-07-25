#!/usr/bin/env python3
"""CI Integration Validation - Validates complete CI pipeline integration
Master Control Program - Final validation of quality enforcement integration.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def validate_file_exists(file_path: Path, description: str) -> bool:
    """Validate that a required file exists."""
    if file_path.exists():
        print(f"✅ {description}: {file_path}")
        return True
    else:
        print(f"❌ {description}: {file_path} - NOT FOUND")
        return False


def validate_ci_workflow() -> bool:
    """Validate GitHub Actions CI workflow."""
    print("🔍 VALIDATING CI WORKFLOW")
    print("-" * 40)
    
    workflow_path = Path('.github/workflows/ci.yml')
    if not validate_file_exists(workflow_path, "CI Workflow"):
        return False
    
    try:
        content = workflow_path.read_text()
        
        # Check for required jobs
        required_jobs = [
            'documentation-quality-gates',
            'lint', 
            'unit-tests',
            'integration-tests',
            'all-tests',
            'rust-quality',
            'security-scan',
            'package'
        ]
        
        missing_jobs = []
        for job in required_jobs:
            if job not in content:
                missing_jobs.append(job)
        
        if missing_jobs:
            print(f"❌ Missing CI jobs: {', '.join(missing_jobs)}")
            return False
        else:
            print(f"✅ All required CI jobs present: {len(required_jobs)} jobs")
        
        # Check for quality enforcement integration
        quality_checks = [
            'Generate test count badge',
            'Generate coverage badge', 
            'Run Rust Quality Checks',
            'Enforce Documentation Quality Gates'
        ]
        
        present_checks = [check for check in quality_checks if check in content]
        print(f"✅ Quality enforcement steps: {len(present_checks)}/{len(quality_checks)}")
        
        return len(missing_jobs) == 0
        
    except Exception as e:
        print(f"❌ Error reading CI workflow: {e}")
        return False


def validate_quality_enforcement() -> bool:
    """Validate quality enforcement system."""
    print("\n🛡️ VALIDATING QUALITY ENFORCEMENT")
    print("-" * 40)
    
    script_path = Path('scripts/enforce_quality.py')
    if not validate_file_exists(script_path, "Quality Enforcement Script"):
        return False
    
    try:
        content = script_path.read_text()
        
        # Check for all quality check types
        check_types = ['format', 'lint', 'type', 'test', 'rust', 'docs', 'badges']
        missing_types = []
        
        for check_type in check_types:
            if f'"{check_type}"' not in content:
                missing_types.append(check_type)
        
        if missing_types:
            print(f"❌ Missing quality check types: {', '.join(missing_types)}")
            return False
        else:
            print(f"✅ All quality check types supported: {len(check_types)} types")
        
        # Check for key classes and functions
        required_components = [
            'class QualityEnforcer',
            'def run_quality_checks',
            'def print_summary',
            'def save_report'
        ]
        
        present_components = [comp for comp in required_components if comp in content]
        print(f"✅ Quality enforcement components: {len(present_components)}/{len(required_components)}")
        
        return len(missing_types) == 0 and len(present_components) == len(required_components)
        
    except Exception as e:
        print(f"❌ Error reading quality enforcement script: {e}")
        return False


def validate_test_badge_system() -> bool:
    """Validate test badge generation system."""
    print("\n🧪 VALIDATING TEST BADGE SYSTEM")
    print("-" * 40)
    
    badge_script = Path('scripts/generate_test_badge.py')
    if not validate_file_exists(badge_script, "Test Badge Generator"):
        return False
    
    # Check for test metrics file
    test_metrics = Path('reports/test_metrics.json')
    if validate_file_exists(test_metrics, "Test Metrics"):
        try:
            with open(test_metrics) as f:
                metrics = json.load(f)
            
            required_fields = ['timestamp', 'python_tests', 'rust_tests', 'total_tests', 'badge_url']
            missing_fields = [field for field in required_fields if field not in metrics]
            
            if missing_fields:
                print(f"❌ Missing metrics fields: {', '.join(missing_fields)}")
                return False
            else:
                print(f"✅ Test metrics complete: {metrics['total_tests']} tests tracked")
                print(f"   • Python tests: {metrics['python_tests']['total']}")
                print(f"   • Rust tests: {metrics['rust_tests']}")
                return True
                
        except Exception as e:
            print(f"❌ Error reading test metrics: {e}")
            return False
    
    return False


def validate_rust_integration() -> bool:
    """Validate Rust quality integration."""
    print("\n🦀 VALIDATING RUST INTEGRATION")
    print("-" * 40)
    
    cargo_toml = Path('zero-engine/Cargo.toml')
    if not validate_file_exists(cargo_toml, "Rust Workspace"):
        print("⚠️ Rust workspace not found - skipping Rust validation")
        return True  # Not required, so return True
    
    try:
        content = cargo_toml.read_text()
        
        # Check for workspace configuration
        if 'workspace' in content and 'resolver = "2"' in content:
            print("✅ Rust workspace properly configured")
        else:
            print("⚠️ Rust workspace configuration could be improved")
        
        # Check for interaction-net crate
        interaction_net = Path('zero-engine/interaction-net/Cargo.toml')
        if validate_file_exists(interaction_net, "Interaction Net Crate"):
            print("✅ Rust crates available for quality checking")
            return True
        else:
            print("⚠️ Rust crates not fully configured")
            return True  # Non-blocking
            
    except Exception as e:
        print(f"❌ Error reading Rust configuration: {e}")
        return True  # Non-blocking


def validate_directory_structure() -> bool:
    """Validate required directory structure."""
    print("\n📁 VALIDATING DIRECTORY STRUCTURE")
    print("-" * 40)
    
    required_dirs = [
        ('reports', 'Quality reports directory'),
        ('artifacts', 'Artifacts storage directory'),
        ('scripts', 'Scripts directory'),
        ('.github/workflows', 'GitHub Actions workflows'),
        ('tests', 'Tests directory'),
        ('src', 'Source code directory')
    ]
    
    all_exist = True
    for dir_path, description in required_dirs:
        path = Path(dir_path)
        if validate_file_exists(path, description):
            continue
        else:
            all_exist = False
    
    return all_exist


def validate_configuration_files() -> bool:
    """Validate configuration files."""
    print("\n⚙️ VALIDATING CONFIGURATION FILES")
    print("-" * 40)
    
    config_files = [
        ('pyproject.toml', 'Python project configuration'),
        ('requirements.txt', 'Python dependencies'),
        ('pytest.ini', 'Pytest configuration'),
        ('.github/workflows/ci.yml', 'CI configuration')
    ]
    
    all_exist = True
    for file_path, description in config_files:
        path = Path(file_path)
        if validate_file_exists(path, description):
            continue
        else:
            all_exist = False
    
    return all_exist


def generate_validation_report() -> Dict:
    """Generate comprehensive validation report."""
    print("\n🔍 RUNNING COMPREHENSIVE CI INTEGRATION VALIDATION")
    print("=" * 60)
    
    validations = [
        ("CI Workflow", validate_ci_workflow),
        ("Quality Enforcement", validate_quality_enforcement), 
        ("Test Badge System", validate_test_badge_system),
        ("Rust Integration", validate_rust_integration),
        ("Directory Structure", validate_directory_structure),
        ("Configuration Files", validate_configuration_files)
    ]
    
    results = {}
    all_passed = True
    
    for name, validator in validations:
        try:
            result = validator()
            results[name] = result
            if not result:
                all_passed = False
        except Exception as e:
            print(f"❌ Validation error in {name}: {e}")
            results[name] = False
            all_passed = False
    
    return {
        'timestamp': Path('reports/quality-check-full.json').stat().st_mtime if Path('reports/quality-check-full.json').exists() else None,
        'overall_status': 'PASSED' if all_passed else 'FAILED',
        'validations': results,
        'summary': {
            'total_checks': len(validations),
            'passed_checks': sum(1 for r in results.values() if r),
            'failed_checks': sum(1 for r in results.values() if not r),
            'success_rate': sum(1 for r in results.values() if r) / len(validations)
        }
    }


def main():
    """Main validation entry point."""
    project_root = Path.cwd()
    print(f"📍 Project root: {project_root}")
    
    # Generate validation report
    report = generate_validation_report()
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 CI INTEGRATION VALIDATION SUMMARY")
    print("=" * 60)
    
    summary = report['summary']
    print(f"✅ Passed: {summary['passed_checks']}")
    print(f"❌ Failed: {summary['failed_checks']}")
    print(f"📈 Success Rate: {summary['passed_checks']}/{summary['total_checks']} ({summary['success_rate']*100:.1f}%)")
    
    print(f"\n🎯 Overall Status: {report['overall_status']}")
    
    # Save validation report
    reports_dir = Path('reports')
    reports_dir.mkdir(exist_ok=True)
    
    report_file = reports_dir / 'ci_validation_report.json'
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"💾 Validation report saved: {report_file}")
    
    if report['overall_status'] == 'PASSED':
        print("\n🎉 CI INTEGRATION VALIDATION PASSED!")
        print("✨ Master Control Program quality enforcement is ready!")
        return 0
    else:
        print("\n🚨 CI INTEGRATION VALIDATION FAILED")
        print("🛠️ Address the issues above to complete integration")
        return 1


if __name__ == '__main__':
    sys.exit(main())