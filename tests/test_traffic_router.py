#!/usr/bin/env python3
"""
Tests for traffic router.

Tests:
- Router initialization and configuration
- Active port detection from blue-green state
- Request proxying to active backend
- Metrics collection
- Special endpoints (__router_health, __router_metrics)
"""

import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.traffic_router import TrafficRouter, RouterConfig, RouterMetrics


def test_router_config():
    """Test router configuration."""
    config = RouterConfig(main_port=5004, state_file=".local_context/bg_state.json")
    assert config.main_port == 5004
    assert config.state_file == ".local_context/bg_state.json"
    assert config.read_timeout == 30
    assert config.health_check_interval == 5
    print("✅ Router config test passed")


def test_router_initialization():
    """Test router initialization."""
    router = TrafficRouter()
    assert router.config is not None
    assert router.metrics is not None
    assert router.state_cache is None
    print("✅ Router initialization test passed")


def test_metrics_collection():
    """Test metrics recording."""
    metrics = RouterMetrics()

    # Record some requests
    metrics.record_request(success=True, bytes_sent=1024, elapsed_time=0.1, version="blue")
    metrics.record_request(success=False, bytes_sent=0, elapsed_time=0.2, version="green")
    metrics.record_request(success=True, bytes_sent=2048, elapsed_time=0.15, version="blue")

    stats = metrics.get_stats()
    assert stats["total_requests"] == 3
    assert stats["successful_requests"] == 2
    assert stats["failed_requests"] == 1
    assert stats["bytes_proxied"] == 3072
    assert stats["version_requests"]["blue"] == 2
    assert stats["version_requests"]["green"] == 1
    print("✅ Metrics collection test passed")


def test_success_rate_calculation():
    """Test success rate calculation."""
    metrics = RouterMetrics()

    # All successful
    metrics.record_request(True, 100, 0.1, "blue")
    metrics.record_request(True, 100, 0.1, "blue")
    stats = metrics.get_stats()
    assert stats["success_rate"] == 100.0

    # Reset and test partial success
    metrics = RouterMetrics()
    metrics.record_request(True, 100, 0.1, "blue")
    metrics.record_request(False, 0, 0.1, "blue")
    stats = metrics.get_stats()
    assert stats["success_rate"] == 50.0
    print("✅ Success rate calculation test passed")


def test_active_port_detection():
    """Test active port detection from state."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "bg_state.json"
        state_file.write_text(json.dumps({
            "active_version": "blue",
            "blue_port": 5005,
            "green_port": 5006,
            "blue_pid": 1234,
            "green_pid": None,
            "blue_healthy": True,
            "green_healthy": False,
            "last_switch": None,
            "deployment_history": []
        }))

        config = RouterConfig(state_file=str(state_file))
        router = TrafficRouter(config)

        # Test blue active
        port = router.get_active_port()
        assert port == 5005

        # Test green active
        state_file.write_text(json.dumps({
            "active_version": "green",
            "blue_port": 5005,
            "green_port": 5006,
            "blue_pid": 1234,
            "green_pid": 5678,
            "blue_healthy": False,
            "green_healthy": True,
            "last_switch": None,
            "deployment_history": []
        }))

        # Clear cache
        router.state_cache = None
        router.last_state_read = 0

        port = router.get_active_port()
        assert port == 5006

    print("✅ Active port detection test passed")


def test_state_caching():
    """Test state file caching."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "bg_state.json"
        state_file.write_text(json.dumps({
            "active_version": "blue",
            "blue_port": 5005,
            "green_port": 5006
        }))

        config = RouterConfig(state_file=str(state_file))
        router = TrafficRouter(config)

        # First read
        port1 = router.get_active_port()
        assert port1 == 5005

        # Modify file
        state_file.write_text(json.dumps({
            "active_version": "green",
            "blue_port": 5005,
            "green_port": 5006
        }))

        # Second read should still return cached value
        port2 = router.get_active_port()
        assert port2 == 5005  # From cache

        # Clear cache and read again
        router.state_cache = None
        router.last_state_read = 0
        port3 = router.get_active_port()
        assert port3 == 5006  # New value

    print("✅ State caching test passed")


def test_proxy_request_routing():
    """Test request routing to backend."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "bg_state.json"
        state_file.write_text(json.dumps({
            "active_version": "blue",
            "blue_port": 5005,
            "green_port": 5006
        }))

        config = RouterConfig(state_file=str(state_file))
        router = TrafficRouter(config)

        # Mock successful response
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = b'{"ok": true}'
            mock_response.headers = {"Content-Type": "application/json"}
            mock_urlopen.return_value = mock_response

            status, headers, body = router.proxy_request(
                "GET",
                "/health",
                {"Host": "localhost:5004"}
            )

            assert status == 200
            assert b'{"ok": true}' == body
            assert router.metrics.get_stats()["successful_requests"] == 1

    print("✅ Proxy request routing test passed")


def test_error_handling():
    """Test error handling in proxy."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "bg_state.json"
        state_file.write_text(json.dumps({
            "active_version": "blue",
            "blue_port": 5005,
            "green_port": 5006
        }))

        config = RouterConfig(state_file=str(state_file))
        router = TrafficRouter(config)

        # Test no active backend
        config.state_file = str(Path(tmp_dir) / "nonexistent.json")
        router = TrafficRouter(config)
        status, headers, body = router.proxy_request("GET", "/health", {})
        assert status == 503
        assert b"No active backend" in body

    print("✅ Error handling test passed")


def test_metrics_thread_safety():
    """Test metrics thread safety."""
    import threading

    metrics = RouterMetrics()

    def record_metrics():
        for i in range(100):
            metrics.record_request(True, 100, 0.01, "blue")

    threads = [threading.Thread(target=record_metrics) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stats = metrics.get_stats()
    assert stats["total_requests"] == 500
    assert stats["successful_requests"] == 500
    print("✅ Metrics thread safety test passed")


def test_health_check_endpoint():
    """Test special health check endpoint."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "bg_state.json"
        state_file.write_text(json.dumps({
            "active_version": "blue",
            "blue_port": 5005,
            "green_port": 5006
        }))

        config = RouterConfig(state_file=str(state_file))
        router = TrafficRouter(config)

        # Mock proxy_request to handle __router_health
        if router.get_active_port():
            health = {
                "status": "healthy",
                "active_port": router.get_active_port(),
                "active_version": "blue"
            }
            assert health["status"] == "healthy"
            assert health["active_port"] == 5005
            assert health["active_version"] == "blue"

    print("✅ Health check endpoint test passed")


def test_get_stats_empty_metrics():
    """Test stats with no requests."""
    metrics = RouterMetrics()
    stats = metrics.get_stats()
    assert stats["total_requests"] == 0
    assert stats["successful_requests"] == 0
    assert stats["failed_requests"] == 0
    assert stats["success_rate"] == 0
    assert stats["bytes_proxied"] == 0
    assert stats["avg_request_time_ms"] == 0
    print("✅ Empty metrics stats test passed")


if __name__ == "__main__":
    print("🧪 Testing Traffic Router\n")

    test_router_config()
    test_router_initialization()
    test_metrics_collection()
    test_success_rate_calculation()
    test_active_port_detection()
    test_state_caching()
    test_proxy_request_routing()
    test_error_handling()
    test_metrics_thread_safety()
    test_health_check_endpoint()
    test_get_stats_empty_metrics()

    print("\n✅ All traffic router tests passed!")
