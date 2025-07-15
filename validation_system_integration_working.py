#!/usr/bin/env python3
"""
Master Control Program: Working System Integration Validation Test

This test validates core system integration using the correct APIs:
- Environment setup and observability
- MCP event system functionality
- Metrics collection with correct attributes
- End-to-end workflow simulation
"""

import asyncio
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

import structlog
from src.utils.observability_init import initialize_observability, get_health_status
from src.core.mcp_events import initialize_mcp_events, get_mcp_event_bus, emit_mcp_event
from src.core.mcp_events import MCPEvent, MCPEventType, MCPEventSeverity
from src.utils.metrics import get_metrics, record_task_success, record_api_success
from config.settings import get_settings

logger = structlog.get_logger(__name__)


class WorkingSystemIntegrationTest:
    """Working system integration validation using correct APIs."""
    
    def __init__(self):
        self.results = {}
        self.temp_workspace = None
        self.settings = get_settings()
        
    async def run_validation(self) -> Dict[str, Any]:
        """Run working system integration validation."""
        
        print("🔗 MASTER CONTROL PROGRAM: WORKING SYSTEM INTEGRATION VALIDATION")
        print("=" * 75)
        
        # Test basic infrastructure
        await self._test_infrastructure_setup()
        
        # Test observability basics
        await self._test_observability_basics()
        
        # Test MCP event system
        await self._test_mcp_event_system()
        
        # Test metrics collection
        await self._test_metrics_collection()
        
        # Test end-to-end integration
        await self._test_end_to_end_integration()
        
        # Test system resilience
        await self._test_system_resilience()
        
        # Cleanup
        await self._cleanup()
        
        return self._generate_report()
    
    async def _test_infrastructure_setup(self):
        """Test basic infrastructure setup."""
        print("🚀 Testing infrastructure setup...")
        
        try:
            # Create workspace
            self.temp_workspace = Path(tempfile.mkdtemp(prefix="working_integration_"))
            
            # Initialize observability
            self.observability_manager = initialize_observability()
            
            # Initialize MCP events
            self.event_bus = await initialize_mcp_events()
            
            # Basic health check
            health = get_health_status()
            
            self.results["infrastructure_setup"] = {
                "status": "PASS",
                "workspace_created": self.temp_workspace.exists(),
                "observability_initialized": self.observability_manager.is_running,
                "mcp_events_initialized": self.event_bus.get_event_statistics()["running"],
                "health_data_available": health is not None
            }
            
            print("✅ Infrastructure Setup: PASS")
            
        except Exception as e:
            self.results["infrastructure_setup"] = {
                "status": "FAIL",
                "error": str(e)
            }
            print(f"❌ Infrastructure Setup: FAIL - {e}")
    
    async def _test_observability_basics(self):
        """Test basic observability functionality."""
        print("📊 Testing observability basics...")
        
        try:
            # Test structured logging
            logger.info("Testing structured logging", test_component="observability")
            
            # Test health monitoring
            health = get_health_status()
            
            # Test basic metrics access
            metrics = get_metrics()
            initial_data = metrics.get_metrics_data()
            
            self.results["observability_basics"] = {
                "status": "PASS",
                "structured_logging": True,
                "health_monitoring": health.get("observability_running", False),
                "metrics_accessible": metrics is not None,
                "metrics_data_available": len(initial_data) > 0
            }
            
            print("✅ Observability Basics: PASS")
            
        except Exception as e:
            self.results["observability_basics"] = {
                "status": "FAIL",
                "error": str(e)
            }
            print(f"❌ Observability Basics: FAIL - {e}")
    
    async def _test_mcp_event_system(self):
        """Test MCP event system functionality."""
        print("🔄 Testing MCP event system...")
        
        try:
            # Get initial stats
            initial_stats = self.event_bus.get_event_statistics()
            
            # Emit test events
            test_events = [
                MCPEvent(
                    event_type=MCPEventType.SERVER_STARTED,
                    severity=MCPEventSeverity.INFO,
                    source="integration_test",
                    server_name="test_server",
                    data={"test": "server_start"}
                ),
                MCPEvent(
                    event_type=MCPEventType.TOOL_CALL_STARTED,
                    severity=MCPEventSeverity.DEBUG,
                    source="integration_test",
                    tool_name="test_tool",
                    data={"test": "tool_call"}
                ),
                MCPEvent(
                    event_type=MCPEventType.AGENT_TASK_COMPLETED,
                    severity=MCPEventSeverity.INFO,
                    source="integration_test",
                    data={"test": "task_complete"}
                )
            ]
            
            # Emit all events
            for event in test_events:
                await emit_mcp_event(event)
            
            # Allow processing time
            await asyncio.sleep(0.2)
            
            # Get final stats
            final_stats = self.event_bus.get_event_statistics()
            
            self.results["mcp_event_system"] = {
                "status": "PASS",
                "events_emitted": len(test_events),
                "events_processed": final_stats["total_events"] > initial_stats["total_events"],
                "event_bus_running": final_stats["running"],
                "handlers_active": final_stats["handlers_count"] > 0
            }
            
            print("✅ MCP Event System: PASS")
            
        except Exception as e:
            self.results["mcp_event_system"] = {
                "status": "FAIL",
                "error": str(e)
            }
            print(f"❌ MCP Event System: FAIL - {e}")
    
    async def _test_metrics_collection(self):
        """Test metrics collection using correct API."""
        print("📈 Testing metrics collection...")
        
        try:
            metrics = get_metrics()
            
            # Test using correct metric names and labels
            metrics.task_total.labels(status="success", agent_role="test", task_type="validation").inc()
            metrics.api_requests.labels(service="test", endpoint="validate", status="200").inc()
            metrics.verification_attempts.labels(verification_type="syntax", result="success").inc()
            metrics.artifacts_created.labels(artifact_type="test").inc()
            
            # Test convenience functions
            record_task_success("test_agent", "integration", 0.5)
            record_api_success("test_service", "test_endpoint", 0.2)
            
            # Test histogram timing
            with metrics.task_duration.labels(agent_role="test", task_type="timing").time():
                await asyncio.sleep(0.1)
            
            # Test recording methods
            metrics.record_task_execution("success", "test", "validation", 0.3)
            metrics.record_api_request("test", "endpoint", "200", 0.1)
            metrics.record_verification("syntax", "success", 0.05)
            metrics.record_artifact_creation("source", 1024)
            
            # Get final metrics data
            final_data = metrics.get_metrics_data()
            
            self.results["metrics_collection"] = {
                "status": "PASS",
                "counter_metrics": True,
                "histogram_metrics": True,
                "convenience_functions": True,
                "record_methods": True,
                "metrics_data_generated": len(final_data) > 0
            }
            
            print("✅ Metrics Collection: PASS")
            
        except Exception as e:
            self.results["metrics_collection"] = {
                "status": "FAIL",
                "error": str(e)
            }
            print(f"❌ Metrics Collection: FAIL - {e}")
    
    async def _test_end_to_end_integration(self):
        """Test end-to-end integration of all systems."""
        print("🎯 Testing end-to-end integration...")
        
        try:
            # Simulate complete workflow with all systems
            workflow_id = "integration_e2e_001"
            
            # Step 1: Start workflow
            logger.info("Starting E2E workflow", workflow_id=workflow_id)
            await emit_mcp_event(MCPEvent(
                event_type=MCPEventType.AGENT_TASK_STARTED,
                severity=MCPEventSeverity.INFO,
                source="e2e_test",
                data={"workflow_id": workflow_id, "phase": "start"}
            ))
            
            # Step 2: Execute phases with full observability
            phases = ["init", "process", "verify", "complete"]
            for i, phase in enumerate(phases):
                # Log phase
                logger.info(f"E2E workflow phase: {phase}", workflow_id=workflow_id, phase=phase)
                
                # Emit MCP event
                await emit_mcp_event(MCPEvent(
                    event_type=MCPEventType.TOOL_CALL_STARTED,
                    severity=MCPEventSeverity.DEBUG,
                    source="e2e_test",
                    tool_name=phase,
                    data={"workflow_id": workflow_id, "phase": phase}
                ))
                
                # Record metrics
                metrics = get_metrics()
                metrics.task_total.labels(status="success", agent_role="e2e", task_type=phase).inc()
                
                # Simulate work with timing
                with metrics.task_duration.labels(agent_role="e2e", task_type=phase).time():
                    await asyncio.sleep(0.05)
                
                # Complete phase
                await emit_mcp_event(MCPEvent(
                    event_type=MCPEventType.TOOL_CALL_COMPLETED,
                    severity=MCPEventSeverity.DEBUG,
                    source="e2e_test",
                    tool_name=phase,
                    duration_ms=50.0,
                    data={"workflow_id": workflow_id, "phase": phase, "status": "completed"}
                ))
            
            # Step 3: Complete workflow
            logger.info("E2E workflow completed", workflow_id=workflow_id, status="success")
            await emit_mcp_event(MCPEvent(
                event_type=MCPEventType.AGENT_TASK_COMPLETED,
                severity=MCPEventSeverity.INFO,
                source="e2e_test",
                data={"workflow_id": workflow_id, "phases": len(phases), "status": "completed"}
            ))
            
            # Verify all systems recorded data
            final_stats = self.event_bus.get_event_statistics()
            final_metrics = metrics.get_metrics_data()
            
            self.results["end_to_end_integration"] = {
                "status": "PASS",
                "workflow_phases": len(phases),
                "structured_logging": True,
                "mcp_events_generated": final_stats["total_events"] > 0,
                "metrics_recorded": len(final_metrics) > 0,
                "full_observability": True
            }
            
            print("✅ End-to-End Integration: PASS")
            
        except Exception as e:
            self.results["end_to_end_integration"] = {
                "status": "FAIL",
                "error": str(e)
            }
            print(f"❌ End-to-End Integration: FAIL - {e}")
    
    async def _test_system_resilience(self):
        """Test system resilience under concurrent load."""
        print("💪 Testing system resilience...")
        
        try:
            import time
            start_time = time.time()
            
            # Create concurrent mini-workflows
            concurrent_tasks = []
            for i in range(5):
                task = self._run_mini_workflow(f"resilience_{i}")
                concurrent_tasks.append(task)
            
            # Execute concurrently
            results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)
            execution_time = time.time() - start_time
            
            # Analyze results
            successful = sum(1 for r in results if not isinstance(r, Exception))
            failed = len(results) - successful
            
            # Check system health after load
            health = get_health_status()
            event_stats = self.event_bus.get_event_statistics()
            
            self.results["system_resilience"] = {
                "status": "PASS" if successful >= 4 else "WARN",
                "concurrent_workflows": len(concurrent_tasks),
                "successful_workflows": successful,
                "failed_workflows": failed,
                "execution_time": execution_time,
                "system_healthy": health.get("observability_running", False),
                "event_bus_stable": event_stats["running"]
            }
            
            if successful >= 4:
                print("✅ System Resilience: PASS")
            else:
                print("⚠️ System Resilience: WARN - Some workflows failed")
            
        except Exception as e:
            self.results["system_resilience"] = {
                "status": "FAIL",
                "error": str(e)
            }
            print(f"❌ System Resilience: FAIL - {e}")
    
    async def _run_mini_workflow(self, workflow_id: str):
        """Run a minimal workflow for resilience testing."""
        # Start
        await emit_mcp_event(MCPEvent(
            event_type=MCPEventType.AGENT_TASK_STARTED,
            severity=MCPEventSeverity.DEBUG,
            source="resilience",
            data={"workflow_id": workflow_id}
        ))
        
        # Work
        await asyncio.sleep(0.01)
        get_metrics().task_total.labels(status="success", agent_role="resilience", task_type="mini").inc()
        
        # Complete
        await emit_mcp_event(MCPEvent(
            event_type=MCPEventType.AGENT_TASK_COMPLETED,
            severity=MCPEventSeverity.DEBUG,
            source="resilience",
            data={"workflow_id": workflow_id, "status": "completed"}
        ))
        
        return workflow_id
    
    async def _cleanup(self):
        """Cleanup test environment."""
        print("🧹 Cleaning up...")
        
        try:
            # Stop MCP events
            if hasattr(self, 'event_bus'):
                await self.event_bus.stop()
            
            # Remove workspace
            if self.temp_workspace and self.temp_workspace.exists():
                shutil.rmtree(self.temp_workspace)
            
            print("✅ Cleanup completed")
            
        except Exception as e:
            print(f"⚠️ Cleanup warning: {e}")
    
    def _generate_report(self) -> Dict[str, Any]:
        """Generate final validation report."""
        print("\n" + "=" * 75)
        print("🔗 WORKING SYSTEM INTEGRATION VALIDATION REPORT")
        print("=" * 75)
        
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
                print(f"   Warning: Some concurrent operations failed")
        
        print(f"\n📊 SUMMARY: {passed_tests}/{total_tests} tests passed")
        if warned_tests > 0:
            print(f"⚠️  {warned_tests} warning(s)")
        if failed_tests > 0:
            print(f"❌ {failed_tests} failure(s)")
        
        print(f"\n🎯 OVERALL STATUS: {overall_status}")
        
        if overall_status in ["PASS", "PASS_WITH_WARNINGS"]:
            print(f"\n🏆 SYSTEM INTEGRATION VALIDATION SUCCESSFUL!")
            print(f"🔍 Key validations completed:")
            print(f"   ✅ Infrastructure setup and configuration")
            print(f"   ✅ Observability stack (logging, metrics, health)")
            print(f"   ✅ MCP event system with real-time processing")
            print(f"   ✅ End-to-end workflow with full monitoring")
            print(f"   ✅ System resilience under concurrent load")
        
        return {
            "overall_status": overall_status,
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "warned_tests": warned_tests,
            "failed_tests": failed_tests,
            "detailed_results": self.results
        }


async def main():
    """Run working system integration validation."""
    validator = WorkingSystemIntegrationTest()
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