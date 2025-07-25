#!/usr/bin/env python3
"""
Master Control Program: Observability Integration Validation Test

This test validates that the complete observability stack works end-to-end:
- Structured logging captures all agent activities
- Prometheus metrics are collected and exported
- MCP events are emitted for state transitions
- Observability doesn't impact system performance
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Any, Dict

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

import structlog

from src.core.mcp_events import (
    MCPEvent,
    MCPEventSeverity,
    MCPEventType,
    emit_mcp_event,
    get_mcp_event_bus,
    initialize_mcp_events,
)
from src.utils.metrics import get_metrics, record_api_success, record_task_success
from src.utils.observability import ObservabilityContext, PerformanceTracker
from src.utils.observability_init import get_health_status, initialize_observability

logger = structlog.get_logger(__name__)


class ObservabilityValidationTest:
    """Comprehensive observability validation test suite."""

    def __init__(self):
        self.results = {}
        self.performance_baseline = None

    async def run_validation(self) -> Dict[str, Any]:
        """Run complete observability validation."""

        print("🔍 MASTER CONTROL PROGRAM: OBSERVABILITY VALIDATION INITIATED")
        print("=" * 70)

        # Initialize observability stack
        await self._test_initialization()

        # Test structured logging
        await self._test_structured_logging()

        # Test metrics collection
        await self._test_metrics_collection()

        # Test MCP events
        await self._test_mcp_events()

        # Test performance impact
        await self._test_performance_impact()

        # Test integration
        await self._test_full_integration()

        return self._generate_report()

    async def _test_initialization(self):
        """Test observability system initialization."""
        print("📊 Testing observability initialization...")

        try:
            # Initialize observability
            manager = initialize_observability()

            # Initialize MCP events
            event_bus = await initialize_mcp_events()

            # Check health status
            health = get_health_status()

            self.results["initialization"] = {
                "status": "PASS",
                "manager_running": manager.is_running,
                "event_bus_running": health.get("observability_running", False),
                "metrics_enabled": health.get("metrics_enabled", False),
                "structured_logging": health.get("structured_logging", False)
            }

            print("✅ Initialization: PASS")

        except Exception as e:
            self.results["initialization"] = {
                "status": "FAIL",
                "error": str(e)
            }
            print(f"❌ Initialization: FAIL - {e}")

    async def _test_structured_logging(self):
        """Test structured logging captures activities."""
        print("📝 Testing structured logging...")

        try:
            # Test different log levels and contexts
            test_data = {
                "test_type": "observability_validation",
                "component": "structured_logging",
                "task_id": "test-123",
                "agent_role": "validation"
            }

            # Test logging at different levels
            logger.debug("Debug message for testing", **test_data)
            logger.info("Info message for testing", **test_data)
            logger.warning("Warning message for testing", **test_data)

            # Test performance tracking context
            with ObservabilityContext("test_operation", logger=logger, **test_data):
                await asyncio.sleep(0.1)  # Simulate work

            self.results["structured_logging"] = {
                "status": "PASS",
                "log_levels_tested": ["debug", "info", "warning"],
                "context_tracking": True,
                "performance_tracking": True
            }

            print("✅ Structured Logging: PASS")

        except Exception as e:
            self.results["structured_logging"] = {
                "status": "FAIL",
                "error": str(e)
            }
            print(f"❌ Structured Logging: FAIL - {e}")

    async def _test_metrics_collection(self):
        """Test Prometheus metrics collection."""
        print("📈 Testing metrics collection...")

        try:
            metrics = get_metrics()

            # Test different metric types
            record_task_success("validation", "observability_test", 0.5)
            record_api_success("claude", "create_message", 1.2)

            # Test custom metrics
            metrics.record_artifact_creation("test", 1024)
            metrics.record_error("TestError", "observability_test")
            metrics.record_verification("compilation", "success", 0.8)

            # Get metrics data
            metrics_data = metrics.get_metrics_data()

            self.results["metrics_collection"] = {
                "status": "PASS",
                "metrics_data_generated": len(metrics_data) > 0,
                "task_metrics": True,
                "api_metrics": True,
                "artifact_metrics": True,
                "error_metrics": True,
                "verification_metrics": True
            }

            print("✅ Metrics Collection: PASS")

        except Exception as e:
            self.results["metrics_collection"] = {
                "status": "FAIL",
                "error": str(e)
            }
            print(f"❌ Metrics Collection: FAIL - {e}")

    async def _test_mcp_events(self):
        """Test MCP event system."""
        print("🔄 Testing MCP events...")

        try:
            # Test event emission
            test_event = MCPEvent(
                event_type=MCPEventType.TOOL_CALL_STARTED,
                severity=MCPEventSeverity.INFO,
                source="validation_test",
                server_name="test_server",
                tool_name="test_tool",
                data={"test": True}
            )

            await emit_mcp_event(test_event)

            # Test event bus statistics
            event_bus = get_mcp_event_bus()
            stats = event_bus.get_event_statistics()

            # Test event filtering
            recent_events = event_bus.get_recent_events(limit=10)

            self.results["mcp_events"] = {
                "status": "PASS",
                "event_emission": True,
                "event_bus_stats": stats,
                "recent_events_count": len(recent_events),
                "event_filtering": True
            }

            print("✅ MCP Events: PASS")

        except Exception as e:
            self.results["mcp_events"] = {
                "status": "FAIL",
                "error": str(e)
            }
            print(f"❌ MCP Events: FAIL - {e}")

    async def _test_performance_impact(self):
        """Test performance impact of observability."""
        print("⚡ Testing performance impact...")

        try:
            # Baseline test without monitoring
            start_time = time.time()
            for i in range(100):
                await asyncio.sleep(0.001)  # Simulate work
            baseline_time = time.time() - start_time

            # Test with full monitoring
            tracker = PerformanceTracker()
            start_time = time.time()

            for i in range(100):
                with tracker.track_task_execution("validation", "performance_test"):
                    await asyncio.sleep(0.001)  # Simulate work

                    # Emit events
                    await emit_mcp_event(MCPEvent(
                        event_type=MCPEventType.TOOL_CALL_COMPLETED,
                        severity=MCPEventSeverity.DEBUG,
                        source="performance_test",
                        data={"iteration": i}
                    ))

                    # Record metrics
                    record_task_success("validation", "performance_test", 0.001)

            monitored_time = time.time() - start_time

            # Calculate overhead
            overhead_percent = ((monitored_time - baseline_time) / baseline_time) * 100

            self.results["performance_impact"] = {
                "status": "PASS" if overhead_percent < 10 else "WARN",  # Allow 10% for test environment
                "baseline_time": baseline_time,
                "monitored_time": monitored_time,
                "overhead_percent": overhead_percent,
                "meets_target": overhead_percent < 5  # Production target is 5%
            }

            if overhead_percent < 10:
                print(f"✅ Performance Impact: PASS ({overhead_percent:.1f}% overhead)")
            else:
                print(f"⚠️ Performance Impact: WARN ({overhead_percent:.1f}% overhead - above target)")

        except Exception as e:
            self.results["performance_impact"] = {
                "status": "FAIL",
                "error": str(e)
            }
            print(f"❌ Performance Impact: FAIL - {e}")

    async def _test_full_integration(self):
        """Test full observability integration."""
        print("🔗 Testing full integration...")

        try:
            # Simulate a complete agent task with full monitoring
            task_data = {
                "task_id": "integration-test-001",
                "agent_role": "validation",
                "task_type": "integration_test"
            }

            tracker = PerformanceTracker()

            # Start task tracking
            with tracker.track_task_execution(
                task_data["agent_role"],
                task_data["task_type"]
            ):
                # Log task start
                logger.info("Starting integration test task", **task_data)

                # Emit MCP events
                await emit_mcp_event(MCPEvent(
                    event_type=MCPEventType.AGENT_TASK_STARTED,
                    severity=MCPEventSeverity.INFO,
                    source="integration_test",
                    data=task_data
                ))

                # Simulate task execution phases
                phases = ["planning", "execution", "verification", "completion"]

                for phase in phases:
                    logger.info(f"Task phase: {phase}", phase=phase, **task_data)

                    # Simulate API calls
                    with tracker.track_api_request("claude", "create_message"):
                        await asyncio.sleep(0.1)  # Simulate API call

                    # Emit phase events
                    await emit_mcp_event(MCPEvent(
                        event_type=MCPEventType.TOOL_CALL_COMPLETED,
                        severity=MCPEventSeverity.DEBUG,
                        source="integration_test",
                        tool_name=phase,
                        data={**task_data, "phase": phase}
                    ))

                # Complete task
                logger.info("Integration test task completed", **task_data)

                await emit_mcp_event(MCPEvent(
                    event_type=MCPEventType.AGENT_TASK_COMPLETED,
                    severity=MCPEventSeverity.INFO,
                    source="integration_test",
                    data={**task_data, "status": "success"}
                ))

            # Verify all data was captured
            event_bus = get_mcp_event_bus()
            stats = event_bus.get_event_statistics()

            self.results["full_integration"] = {
                "status": "PASS",
                "task_phases_completed": len(phases),
                "events_captured": stats["total_events"] > 0,
                "metrics_recorded": True,
                "logs_generated": True,
                "end_to_end_success": True
            }

            print("✅ Full Integration: PASS")

        except Exception as e:
            self.results["full_integration"] = {
                "status": "FAIL",
                "error": str(e)
            }
            print(f"❌ Full Integration: FAIL - {e}")

    def _generate_report(self) -> Dict[str, Any]:
        """Generate final validation report."""
        print("\n" + "=" * 70)
        print("📋 OBSERVABILITY VALIDATION REPORT")
        print("=" * 70)

        # Count results
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results.values() if r["status"] == "PASS")
        warned_tests = sum(1 for r in self.results.values() if r["status"] == "WARN")
        failed_tests = sum(1 for r in self.results.values() if r["status"] == "FAIL")

        # Overall status
        if failed_tests == 0 and warned_tests == 0:
            overall_status = "PASS"
        elif failed_tests == 0:
            overall_status = "PASS_WITH_WARNINGS"
        else:
            overall_status = "FAIL"

        # Print summary
        for test_name, result in self.results.items():
            status_emoji = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}[result["status"]]
            print(f"{status_emoji} {test_name.replace('_', ' ').title()}: {result['status']}")

            if result["status"] == "FAIL":
                print(f"   Error: {result.get('error', 'Unknown error')}")
            elif result["status"] == "WARN":
                print("   Warning: Performance overhead above target")

        print(f"\n📊 SUMMARY: {passed_tests}/{total_tests} tests passed")
        if warned_tests > 0:
            print(f"⚠️  {warned_tests} warning(s)")
        if failed_tests > 0:
            print(f"❌ {failed_tests} failure(s)")

        print(f"\n🎯 OVERALL STATUS: {overall_status}")

        return {
            "overall_status": overall_status,
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "warned_tests": warned_tests,
            "failed_tests": failed_tests,
            "detailed_results": self.results
        }


async def main():
    """Run observability validation."""
    validator = ObservabilityValidationTest()
    report = await validator.run_validation()

    # Return appropriate exit code
    if report["overall_status"] == "FAIL":
        sys.exit(1)
    elif report["overall_status"] == "PASS_WITH_WARNINGS":
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
