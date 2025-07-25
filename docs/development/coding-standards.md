# Coding Standards

**Reality Validation**: Standards enforced by CI - [Enforcement Scripts](../validation/standards_validator.py)

## Code Quality Requirements

### Formatting Standards
- **Black**: Code formatting enforced by CI
- **Line Length**: 88 characters maximum
- **Import Sorting**: isort for consistent import organization

**Validation Command**: 
```bash
python docs/validation/standards_validator.py --check-formatting
```

### Linting Requirements
- **Ruff**: Primary linter with strict configuration
- **Zero Warnings**: CI fails on any linting warnings
- **Custom Rules**: Project-specific rules in `.ruff.toml`

**Validation Command**:
```bash
python docs/validation/standards_validator.py --check-linting
```

### Type Checking
- **MyPy**: Type checking required for all new code
- **Coverage**: Minimum 80% type annotation coverage
- **Strict Mode**: Enabled for core modules

**Validation Command**:
```bash
python docs/validation/standards_validator.py --check-typing
```

## Documentation Requirements

### Code Documentation
- **Docstrings**: Required for all public functions and classes
- **Type Hints**: Required for all function parameters and returns
- **Examples**: Include usage examples in docstrings

**Example**:
```python
def process_request(request: str, timeout: int = 30) -> ProcessResult:
    """Process a user request with specified timeout.
    
    Args:
        request: The user request to process
        timeout: Maximum processing time in seconds
        
    Returns:
        ProcessResult containing success status and response
        
    Example:
        >>> result = process_request("Create hello world", timeout=60)
        >>> print(result.success)
        True
    """
```

### Architecture Documentation
- **Module Purpose**: Each module must have clear purpose documentation
- **Dependencies**: Document all external dependencies
- **Configuration**: Document all configuration options

## Testing Requirements

### Test Coverage
- **Minimum Coverage**: 90% line coverage required
- **Branch Coverage**: 85% branch coverage required
- **Critical Paths**: 100% coverage for critical functionality

**Validation Command**:
```bash
python docs/validation/standards_validator.py --check-coverage
```

### Test Quality
- **Test Naming**: Descriptive test names following `test_<action>_<expected_result>` pattern
- **Test Documentation**: Test purposes documented in docstrings
- **Test Data**: Use fixtures for consistent test data

## Performance Standards

### Response Time Requirements
- **API Calls**: < 5 seconds for simple requests
- **Task Processing**: < 30 seconds for basic tasks
- **Health Checks**: < 2 seconds for system health validation

**Benchmarking Command**:
```bash
python docs/validation/standards_validator.py --check-performance
```

### Resource Usage
- **Memory**: Peak usage < 1GB for standard operations
- **CPU**: < 80% CPU utilization during normal operation
- **Disk**: Efficient artifact storage with compression

## Security Standards

### Code Security
- **No Hardcoded Secrets**: All secrets must be in environment variables
- **Input Validation**: All user inputs must be validated
- **Error Handling**: No sensitive information in error messages

**Security Validation**:
```bash
python docs/validation/standards_validator.py --check-security
```

### Dependency Security
- **Vulnerability Scanning**: All dependencies scanned for known vulnerabilities
- **Regular Updates**: Dependencies updated monthly
- **License Compliance**: All dependencies use approved licenses

## Quality Gates

### Pre-commit Requirements
All code must pass these checks before commit:
1. **Formatting**: Black formatting applied
2. **Linting**: Ruff checks pass with zero warnings
3. **Type Checking**: MyPy validation successful
4. **Tests**: All tests pass with required coverage
5. **Security**: Security scans show no critical issues

### CI Requirements
Additional CI-only checks:
1. **Integration Tests**: Full integration test suite passes
2. **Performance Tests**: Performance benchmarks meet standards
3. **Documentation**: All documentation links are valid
4. **Examples**: All documented examples execute successfully

## Enforcement

### Automated Enforcement
- **Pre-commit Hooks**: Standards enforced before commit
- **CI Pipeline**: Comprehensive validation in CI
- **Quality Gates**: Deployment blocked on standard violations

### Manual Review Requirements
- **Code Review**: All changes require peer review
- **Architecture Review**: Significant changes require architecture review
- **Security Review**: Security-sensitive changes require security review

---

**Enforcement Status**: Standards automatically enforced by CI
**Compliance Rate**: Tracked in [metrics/standards-compliance.json](../metrics/standards-compliance.json)
**Last Updated**: Standards configuration synced with CI on each run