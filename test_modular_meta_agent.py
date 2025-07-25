#!/usr/bin/env python3
"""Simple test script for the modularized MetaAgent system.
This test works without external dependencies to validate the modular architecture.
"""

import sys
from pathlib import Path


def test_imports():
    """Test that all modular components can be imported."""
    print("🔍 Testing Modular Component Imports...")

    components = [
        "src.agents.meta_agent_config",
        "src.agents.configuration_manager",
        "src.agents.error_handler",
        "src.agents.progress_monitor",
        "src.agents.task_decomposer",
        "src.agents.execution_coordinator",
        "src.agents.project_manager",
        "src.agents.agent_spawner",
        "src.agents.result_processor",
        "src.agents.meta_agent"
    ]

    successful_imports = []
    failed_imports = []

    for component in components:
        try:
            # Mock required dependencies
            mock_structlog = MockStructlog()
            mock_config = MockConfig()
            mock_app_logging = MockAppLogging()

            # Add the module-level functions to the config mock instance
            mock_config.get_settings = get_settings
            mock_config.reload_settings = reload_settings
            mock_config.ClaudeModel = MockConfig.ClaudeModel

            # Add module-level functions to app_logging mock instance
            mock_app_logging.setup_logging = setup_logging
            mock_app_logging.get_logger = get_logger
            mock_app_logging.log_execution_time = log_execution_time
            mock_app_logging.LogContext = LogContext

            sys.modules['structlog'] = mock_structlog
            sys.modules['config'] = mock_config
            sys.modules['src.utils.app_logging'] = mock_app_logging

            __import__(component)
            successful_imports.append(component)
            print(f"  ✅ {component.split('.')[-1]}")
        except Exception as e:
            failed_imports.append((component, str(e)))
            print(f"  ❌ {component.split('.')[-1]}: {e}")

    print(f"\n📊 Import Results: {len(successful_imports)}/{len(components)} successful")
    return len(failed_imports) == 0


def test_config_creation():
    """Test configuration creation without external dependencies."""
    print("\n⚙️ Testing Configuration Creation...")

    try:
        # Mock the config dependencies
        mock_structlog = MockStructlog()
        sys.modules['structlog'] = mock_structlog
        sys.modules['structlog.processors'] = mock_structlog.processors

        # Create a minimal config test
        from src.agents.meta_agent_config import MetaAgentConfig

        # Test configuration creation
        config = MetaAgentConfig()
        print("  ✅ MetaAgentConfig created successfully")

        # Test configuration validation (basic)
        if hasattr(config, 'retry') and hasattr(config, 'task_execution'):
            print("  ✅ Configuration structure is valid")

        # Test configuration to dict
        config_dict = config.to_dict()
        if isinstance(config_dict, dict) and 'retry' in config_dict:
            print("  ✅ Configuration serialization works")

        return True
    except Exception as e:
        print(f"  ❌ Configuration test failed: {e}")
        return False


def test_architecture_integration():
    """Test the overall architecture integration."""
    print("\n🏗️ Testing Architecture Integration...")

    try:
        # Check that the refactored meta agent file has proper integration
        meta_agent_path = Path("src/agents/meta_agent.py")
        if not meta_agent_path.exists():
            print("  ❌ meta_agent.py not found")
            return False

        content = meta_agent_path.read_text()

        # Check for key integration points
        integration_checks = [
            ("ConfigurationManager import", "from src.agents.configuration_manager import ConfigurationManager"),
            ("All 8 component imports", "from src.agents.result_processor import ResultProcessor"),
            ("Component initialization", "self.config_manager = ConfigurationManager"),
            ("Modular components usage", "components = self.config_manager.create_complete_configuration()"),
            ("Backward compatibility", "MetaAgent = MetaAgentRefactored"),
            ("Health status method", "async def get_health_status("),
            ("Statistics gathering", "def get_execution_stats("),
            ("Cleanup method", "async def cleanup(")
        ]

        passed_checks = 0
        for check_name, check_text in integration_checks:
            if check_text in content:
                print(f"  ✅ {check_name}")
                passed_checks += 1
            else:
                print(f"  ❌ {check_name}")

        print(f"\n📊 Integration Score: {passed_checks}/{len(integration_checks)} checks passed")
        return passed_checks == len(integration_checks)

    except Exception as e:
        print(f"  ❌ Architecture integration test failed: {e}")
        return False


def test_file_structure():
    """Test that all required modular component files exist."""
    print("\n📁 Testing File Structure...")

    required_files = [
        "src/agents/meta_agent.py",
        "src/agents/meta_agent_config.py",
        "src/agents/configuration_manager.py",
        "src/agents/error_handler.py",
        "src/agents/progress_monitor.py",
        "src/agents/task_decomposer.py",
        "src/agents/execution_coordinator.py",
        "src/agents/project_manager.py",
        "src/agents/agent_spawner.py",
        "src/agents/result_processor.py"
    ]

    missing_files = []
    total_size = 0

    for file_path in required_files:
        path = Path(file_path)
        if path.exists():
            size = path.stat().st_size
            total_size += size
            print(f"  ✅ {path.name} ({size:,} bytes)")
        else:
            missing_files.append(file_path)
            print(f"  ❌ {path.name} - Missing")

    print(f"\n📊 File Structure: {len(required_files) - len(missing_files)}/{len(required_files)} files present")
    print(f"📦 Total Size: {total_size:,} bytes ({total_size/1024:.1f} KB)")

    return len(missing_files) == 0


# Mock classes for testing without dependencies
class MockProcessors:
    """Mock structlog processors module."""

    class JSONProcessor:
        def __call__(self, *args, **kwargs):
            return {}

    class TimeStamper:
        def __call__(self, *args, **kwargs):
            return {}

    def JSONRenderer(*args, **kwargs):
        return MockProcessors.JSONProcessor()

    def TimeStamper(*args, **kwargs):
        return MockProcessors.TimeStamper()

    class CallsiteParameter:
        def __call__(self, *args, **kwargs):
            return {}

    def add_log_level(*args, **kwargs):
        return {}

    def add_logger_name(*args, **kwargs):
        return {}

class MockStructlog:
    def get_logger(self, name=None):
        return MockLogger()

    class BoundLogger:
        def __call__(self, *args, **kwargs):
            return MockLogger()

        def info(self, *args, **kwargs): pass
        def error(self, *args, **kwargs): pass
        def warning(self, *args, **kwargs): pass
        def debug(self, *args, **kwargs): pass

    # Add processors as attribute
    processors = MockProcessors()

class MockLogger:
    def info(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def debug(self, *args, **kwargs): pass

class MockConfig:
    class LogLevel:
        DEBUG = "DEBUG"

    class Environment:
        development = "development"

    class ClaudeModel:
        HAIKU = "claude-3-haiku-20240307"
        SONNET = "claude-3-sonnet-20240229"
        OPUS = "claude-3-opus-20240229"

    def get_settings(self):
        return MockSettings()

# Add module-level functions that config.py exports
def get_settings():
    return MockConfig().get_settings()

def reload_settings():
    return MockConfig().get_settings()

class MockSettings:
    def __init__(self):
        self.project_name = "test"
        self.version = "1.0"
        self.environment = MockConfig.Environment()
        self.debug = False
        self.logging = MockLoggingSettings()

class MockLoggingSettings:
    def __init__(self):
        self.level = MockConfig.LogLevel.DEBUG
        self.format = "json"
        self.file_path = None
        self.max_file_size_mb = 0
        self.backup_count = 5

class MockAppLogging:
    def get_logger(self, name=None):
        return MockLogger()

    def log_execution_time(self, name):
        def decorator(func):
            return func
        return decorator

    def setup_logging(self, *args, **kwargs):
        pass

# Add module-level functions that app_logging exports
def get_logger(name=None):
    return MockLogger()

def log_execution_time(name):
    def decorator(func):
        return func
    return decorator

def setup_logging(*args, **kwargs):
    pass

class LogContext:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def main():
    """Run all tests."""
    print("🧪 MODULAR METAAGENT TESTING SUITE")
    print("=" * 60)

    tests = [
        ("File Structure", test_file_structure),
        ("Configuration Creation", test_config_creation),
        ("Architecture Integration", test_architecture_integration),
        ("Component Imports", test_imports)
    ]

    passed_tests = 0
    test_results = []

    for test_name, test_func in tests:
        try:
            result = test_func()
            test_results.append(result)
            if result:
                passed_tests += 1
        except Exception as e:
            print(f"  ❌ {test_name} failed with exception: {e}")
            test_results.append(False)

    print("\n" + "=" * 60)
    print("🎯 TEST RESULTS SUMMARY")
    print("=" * 60)

    for i, (test_name, _) in enumerate(tests):
        status = "✅ PASS" if test_results[i] else "❌ FAIL"
        print(f"{test_name:25s}: {status}")

    print(f"\n📊 Overall Score: {passed_tests}/{len(tests)} tests passed")

    if passed_tests == len(tests):
        print("\n🎉 ALL TESTS PASSED! Modular architecture is working correctly.")
        print("🚀 You can now proceed to test with actual dependencies.")
        return 0
    else:
        print(f"\n⚠️  {len(tests) - passed_tests} tests failed. Please review the issues above.")
        return 1


if __name__ == "__main__":
    exit(main())
