"""Unit tests for the health check system."""


import pytest

from src.utils.health_check import (
    HealthCheckResult,
    SystemHealthChecker,
    validate_system_health,
)


class TestHealthCheckResult:
    """Test HealthCheckResult class."""

    def test_health_check_result_creation(self):
        """Test creating a health check result."""
        result = HealthCheckResult(
            component="test_component",
            status="OK",
            message="Test passed",
            details={"foo": "bar"}
        )

        assert result.component == "test_component"
        assert result.status == "OK"
        assert result.message == "Test passed"
        assert result.details == {"foo": "bar"}
        assert result.is_healthy is True

    def test_health_check_result_unhealthy(self):
        """Test unhealthy result."""
        result = HealthCheckResult(
            component="test_component",
            status="ERROR",
            message="Test failed"
        )

        assert result.is_healthy is False

    def test_health_check_result_to_dict(self):
        """Test converting result to dictionary."""
        result = HealthCheckResult(
            component="test_component",
            status="WARNING",
            message="Test warning",
            details={"level": "minor"}
        )

        result_dict = result.to_dict()
        assert result_dict["component"] == "test_component"
        assert result_dict["status"] == "WARNING"
        assert result_dict["message"] == "Test warning"
        assert result_dict["details"] == {"level": "minor"}
        assert "timestamp" in result_dict


class TestSystemHealthChecker:
    """Test SystemHealthChecker class."""

    @pytest.mark.asyncio
    async def test_check_python_version(self):
        """Test Python version check."""
        checker = SystemHealthChecker()
        await checker._check_python_version()

        assert len(checker.results) == 1
        result = checker.results[0]
        assert result.component == "python_version"
        # Should pass on Python 3.9+
        assert result.status == "OK"

    @pytest.mark.asyncio
    async def test_check_required_directories(self, tmp_path, monkeypatch):
        """Test directory check."""
        # Change to temp directory
        monkeypatch.chdir(tmp_path)

        checker = SystemHealthChecker()
        await checker._check_required_directories()

        assert len(checker.results) == 1
        result = checker.results[0]
        assert result.component == "directories"
        assert result.status == "OK"

        # Verify directories were created
        for dir_name in ["config", "src", "tests", "artifacts", "logs"]:
            assert (tmp_path / dir_name).exists()

    @pytest.mark.asyncio
    async def test_check_dependencies(self):
        """Test dependency check."""
        checker = SystemHealthChecker()
        await checker._check_dependencies()

        assert len(checker.results) == 1
        result = checker.results[0]
        assert result.component == "dependencies"
        # Should pass if all dependencies are installed
        assert result.status in ["OK", "ERROR"]

    @pytest.mark.asyncio
    async def test_compile_results(self):
        """Test result compilation."""
        checker = SystemHealthChecker()

        # Add some test results
        checker.results = [
            HealthCheckResult("comp1", "OK", "Test 1 OK"),
            HealthCheckResult("comp2", "WARNING", "Test 2 Warning"),
            HealthCheckResult("comp3", "ERROR", "Test 3 Error"),
            HealthCheckResult("comp4", "OK", "Test 4 OK"),
        ]

        compiled = checker._compile_results()

        assert compiled["status"] == "UNHEALTHY"  # Due to error
        assert compiled["summary"]["total_checks"] == 4
        assert compiled["summary"]["healthy"] == 2
        assert compiled["summary"]["warnings"] == 1
        assert compiled["summary"]["errors"] == 1
        assert len(compiled["checks"]) == 4


class TestValidateSystemHealth:
    """Test the main validation function."""

    @pytest.mark.asyncio
    async def test_validate_system_health(self, monkeypatch, tmp_path):
        """Test full system health validation."""
        # Set up minimal environment
        monkeypatch.setenv("ACS_API__KEY", "test-key")
        monkeypatch.chdir(tmp_path)

        is_healthy, results = await validate_system_health()

        # Should return results dictionary
        assert isinstance(results, dict)
        assert "status" in results
        assert "summary" in results
        assert "checks" in results

        # Should have run multiple checks
        assert results["summary"]["total_checks"] > 0

    @pytest.mark.asyncio
    async def test_validate_system_health_without_api_key(self, monkeypatch, tmp_path):
        """Test health check without API key."""
        # Remove API key and set to empty string to trigger error
        monkeypatch.setenv("ACS_API__KEY", "")
        monkeypatch.chdir(tmp_path)

        # Need to reload settings to pick up the empty API key
        from config import reload_settings
        reload_settings()

        is_healthy, results = await validate_system_health()

        # Should still complete but mark as unhealthy
        assert is_healthy is False
        assert results["status"] in ["UNHEALTHY", "DEGRADED"]

        # Should have api_config error
        api_checks = [c for c in results["checks"] if c["component"] == "api_config"]
        assert any(c["status"] == "ERROR" for c in api_checks)
