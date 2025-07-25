# Agentic Coding System Documentation

**Single Source of Truth for All System Documentation**

This documentation follows three core guiding principles:

1. **Reality > Aspirations**: Every claim links to verifiable running code, tests, or metrics
2. **One-touch Truth-source**: All process descriptions live in /docs/, enforced by CI
3. **Fail Fast, Fix Fast**: CI breaks the moment docs or quality gates drift

## Documentation Structure

### 🚀 [Development](development/)
- [Setup Process](development/setup.md) - Complete development environment setup
- [Coding Standards](development/coding-standards.md) - Enforced code quality standards
- [Testing Procedures](development/testing.md) - Testing requirements and processes
- [CI/CD Processes](development/ci-cd.md) - Continuous integration and deployment

### 🏗️ [Architecture](architecture/)
- [System Overview](architecture/overview.md) - High-level system architecture
- [Component Documentation](architecture/components.md) - Detailed component descriptions
- [Data Flow](architecture/data-flow.md) - System data flow and interactions

### 📖 [User Guide](user-guide/)
- [Installation](user-guide/installation.md) - System installation instructions
- [Usage Examples](user-guide/usage.md) - Practical usage examples
- [Troubleshooting](user-guide/troubleshooting.md) - Problem resolution guide

### 🔌 [API Reference](api/)
- [API Documentation](api/reference.md) - Complete API reference
- [Usage Examples](api/examples.md) - API usage examples

### ✅ [Validation](validation/)
- [Documentation Validator](validation/doc_validator.py) - Automated validation tools
- [Reality Checker](validation/reality_checker.py) - Reality alignment verification
- [Metrics Validator](validation/metrics_validator.py) - Performance metrics validation

### 📋 [Processes](processes/)
- [Development Workflow](processes/development-workflow.md) - Standard development process
- [Code Review Process](processes/code-review.md) - Code review requirements
- [Quality Gates](processes/quality-gates.md) - Quality enforcement standards

### 📊 [Metrics](metrics/)
- [Performance Benchmarks](metrics/performance.md) - System performance metrics
- [Test Coverage](metrics/coverage.md) - Test coverage reports
- [Quality Metrics](metrics/quality.md) - Code quality measurements

## Documentation Standards

### Reality Validation Requirements
- **Code Claims**: Must link to actual implementation files
- **Performance Claims**: Must reference real benchmark data
- **Process Claims**: Must link to executable scripts
- **Examples**: Must be runnable and tested in CI

### Documentation Principles
- Every feature claim must be verifiable
- All examples must be executable
- All processes must be implementable
- All metrics must be measurable

### Quality Gates
- Documentation completeness validation
- Code reference verification
- Example execution testing
- Metrics accuracy checking

---

**Status**: This documentation is automatically validated by CI and represents the current system reality.

**Last Validated**: Automatically updated on each CI run