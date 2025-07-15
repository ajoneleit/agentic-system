# Phase 4 Verification System - Test Guide

This guide lists all tests for the Basic Verification System (Phase 4) and how to run them.

## Main Test Files

### 1. **tests/test_verification_system.py** (Comprehensive Test Suite)
The main test file with full coverage of the verification system.

**Test Classes:**
- `TestPythonVerifier` - Tests Python syntax and compilation verification
- `TestJavaScriptVerifier` - Tests JavaScript syntax verification
- `TestPythonTestVerifier` - Tests Python test execution verification
- `TestVerificationPipeline` - Tests the verification pipeline orchestrator
- `TestRepairAnalyzer` - Tests the repair analyzer
- `TestVerifierFactory` - Tests the verifier factory function
- `TestVerificationConfig` - Tests verification configuration
- `TestVerificationIntegration` - Integration tests

**How to run:**
```bash
# From project root (/mnt/c/Users/ajoneleit/agentic-system/)
python -m pytest tests/test_verification_system.py -v

# Run specific test class
python -m pytest tests/test_verification_system.py::TestPythonVerifier -v

# Run specific test method
python -m pytest tests/test_verification_system.py::TestPythonTestVerifier::test_passing_tests -v
```

### 2. **test_verification_standalone.py** (No Dependencies)
Standalone tests that don't require external dependencies like pydantic or structlog.

**Features:**
- Mock implementations of all required classes
- Tests core verification functionality
- Can run without installing dependencies

**How to run:**
```bash
python test_verification_standalone.py
```

### 3. **test_verification_minimal.py** (Minimal Tests)
Minimal test suite focusing on essential functionality.

**How to run:**
```bash
python test_verification_minimal.py
```

### 4. **test_verification_core.py** (Core Functionality)
Tests core verification components in isolation.

**How to run:**
```bash
python test_verification_core.py
```

### 5. **test_verification_integration.py** (Integration Tests)
Tests integration between different verification components.

**How to run:**
```bash
python test_verification_integration.py
```

## Utility Test Files

### 6. **test_verification_fix.py**
Tests the specific fix for pytest test discovery issue.

**How to run:**
```bash
python test_verification_fix.py
```

### 7. **verify_pytest_fix.py**
Verifies that pytest can discover tests with the naming fix.

**How to run:**
```bash
python verify_pytest_fix.py
```

### 8. **test_json_report.py**
Tests pytest plugin availability and fallback behavior.

**How to run:**
```bash
python test_json_report.py
```

### 9. **test_fix_complete.py**
Complete end-to-end test of the PythonTestVerifier fix.

**How to run:**
```bash
python test_fix_complete.py
```

## Running All Tests

### Option 1: Using pytest (Requires Dependencies)
```bash
# Install required dependencies first
pip install pydantic structlog pytest pytest-asyncio

# Run all verification tests
python -m pytest tests/test_verification_system.py -v

# Run with coverage
python -m pytest tests/test_verification_system.py --cov=src.verification --cov-report=html
```

### Option 2: Using Standalone Tests (No Dependencies)
```bash
# Run each standalone test file
python test_verification_standalone.py
python test_verification_minimal.py
python test_verification_core.py
python test_verification_integration.py
```

### Option 3: Using the Test Runner Script
```bash
# If available, use the test runner
python run_tests.py --verification
```

## Test Coverage

The tests cover:

1. **Syntax Verification**
   - Python syntax checking
   - JavaScript syntax checking
   - TypeScript syntax checking

2. **Compilation Verification**
   - Python compilation
   - Import checking
   - Error detection and reporting

3. **Test Execution**
   - pytest integration
   - Test discovery and counting
   - Coverage reporting
   - Failure analysis

4. **Pipeline Orchestration**
   - Multi-artifact verification
   - Parallel execution
   - Dependency handling
   - Result aggregation

5. **Repair Analysis**
   - Error pattern detection
   - Suggestion generation
   - Repair prompt creation

6. **Configuration**
   - Default settings
   - Custom configurations
   - Language-specific settings

## Common Issues and Solutions

### Issue: ModuleNotFoundError
**Solution:** Use one of these methods:
```bash
# Method 1: Use python -m
python -m pytest tests/test_verification_system.py

# Method 2: Set PYTHONPATH
export PYTHONPATH=/mnt/c/Users/ajoneleit/agentic-system:$PYTHONPATH
pytest tests/test_verification_system.py

# Method 3: Use standalone tests
python test_verification_standalone.py
```

### Issue: Missing Dependencies
**Solution:** Either install dependencies or use standalone tests:
```bash
# Install dependencies
pip install pydantic structlog pytest pytest-asyncio

# Or use standalone tests that don't need dependencies
python test_verification_standalone.py
```

### Issue: pytest plugins not available
**Solution:** The verification system automatically detects and handles missing plugins:
- Falls back to text parsing if pytest-json-report is not available
- Skips timeout if pytest-timeout is not available
- Skips coverage if pytest-cov is not available

## Test Results Summary

When all tests pass, you should see:
- ✅ Syntax verification working for Python, JavaScript, TypeScript
- ✅ Compilation checks detecting errors correctly
- ✅ Test execution finding and running all tests
- ✅ Pipeline orchestrating multiple verifications
- ✅ Repair analyzer generating appropriate suggestions
- ✅ Configuration system working as expected

Total expected tests: ~35 test methods across all test files