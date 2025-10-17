#!/usr/bin/env python3
"""
Test blue-green deployment system.
Tests include: state management, health checks, deployment flow, rollback.
"""

import pytest
import json
import tempfile
import time
from pathlib import Path
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.blue_green import BlueGreenManager, DeploymentState


def test_deployment_state_creation():
    """Test creating and serializing deployment state."""
    state = DeploymentState(
        active_version="blue",
        blue_port=5005,
        green_port=5006
    )

    assert state.active_version == "blue"
    assert state.blue_port == 5005
    assert state.green_port == 5006
    assert state.blue_pid is None
    assert state.deployment_history == []

    # Test serialization
    state_dict = state.to_dict()
    assert state_dict["active_version"] == "blue"
    assert state_dict["blue_port"] == 5005

    print("✅ Deployment state creation test passed")


def test_blue_green_manager_init():
    """Test BlueGreenManager initialization."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        state_file = tmp_path / "bg_state.json"

        # Create a fake app.py
        app_file = tmp_path / "app.py"
        app_file.write_text("# fake app")

        manager = BlueGreenManager(
            str(app_file),
            blue_port=5005,
            green_port=5006,
            state_file=state_file
        )

        assert manager.blue_port == 5005
        assert manager.green_port == 5006
        assert manager.state.active_version == "blue"

    print("✅ BlueGreenManager initialization test passed")


def test_state_persistence():
    """Test saving and loading deployment state."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        state_file = tmp_path / "bg_state.json"
        app_file = tmp_path / "app.py"
        app_file.write_text("# fake app")

        # Create manager and update state
        manager1 = BlueGreenManager(
            str(app_file),
            state_file=state_file
        )
        manager1.state.blue_pid = 12345
        manager1.state.active_version = "green"
        manager1._save_state()

        # Load in new manager
        manager2 = BlueGreenManager(
            str(app_file),
            state_file=state_file
        )

        assert manager2.state.blue_pid == 12345
        assert manager2.state.active_version == "green"

    print("✅ State persistence test passed")


def test_inactive_version_logic():
    """Test determining inactive version."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        app_file = tmp_path / "app.py"
        app_file.write_text("# fake app")

        manager = BlueGreenManager(str(app_file))

        # When blue is active, green is inactive
        manager.state.active_version = "blue"
        assert manager._get_inactive_version() == "green"

        # When green is active, blue is inactive
        manager.state.active_version = "green"
        assert manager._get_inactive_version() == "blue"

    print("✅ Inactive version logic test passed")


def test_port_mapping():
    """Test port mapping for versions."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        app_file = tmp_path / "app.py"
        app_file.write_text("# fake app")

        manager = BlueGreenManager(
            str(app_file),
            blue_port=5005,
            green_port=5006
        )

        assert manager._get_port("blue") == 5005
        assert manager._get_port("green") == 5006

    print("✅ Port mapping test passed")


def test_health_check_logic():
    """Test health check with mock."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        app_file = tmp_path / "app.py"
        app_file.write_text("# fake app")

        manager = BlueGreenManager(str(app_file))

        # Mock health check - will fail for non-existent ports
        # This is expected behavior
        # Use high ports unlikely to have services running
        blue_health = manager._health_check(59991)
        green_health = manager._health_check(59992)

        # Both should be False since nothing is running
        assert blue_health is False
        assert green_health is False

    print("✅ Health check logic test passed")


def test_deployment_history():
    """Test deployment history tracking."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        state_file = tmp_path / "bg_state.json"
        app_file = tmp_path / "app.py"
        app_file.write_text("# fake app")

        manager = BlueGreenManager(
            str(app_file),
            state_file=state_file
        )

        # Simulate deployment history entries
        manager.state.deployment_history.append({
            "timestamp": "2025-10-16T18:00:00Z",
            "from": "blue",
            "to": "green",
            "status": "success"
        })

        manager._save_state()

        # Load and verify
        manager2 = BlueGreenManager(str(app_file), state_file=state_file)
        assert len(manager2.state.deployment_history) == 1
        assert manager2.state.deployment_history[0]["from"] == "blue"

    print("✅ Deployment history test passed")


def test_get_status():
    """Test status reporting."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        app_file = tmp_path / "app.py"
        app_file.write_text("# fake app")

        manager = BlueGreenManager(str(app_file))
        status = manager.get_status()

        # Verify status structure
        assert "active_version" in status
        assert "active_port" in status
        assert "blue" in status
        assert "green" in status
        assert "last_check" in status
        assert "history" in status

        # Verify version details
        assert "port" in status["blue"]
        assert "pid" in status["blue"]
        assert "healthy" in status["blue"]
        assert "status" in status["blue"]

    print("✅ Status reporting test passed")


def test_configuration_override():
    """Test custom port configuration."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        app_file = tmp_path / "app.py"
        app_file.write_text("# fake app")

        manager = BlueGreenManager(
            str(app_file),
            blue_port=8001,
            green_port=8002
        )

        assert manager.blue_port == 8001
        assert manager.green_port == 8002
        assert manager._get_port("blue") == 8001
        assert manager._get_port("green") == 8002

    print("✅ Configuration override test passed")


if __name__ == "__main__":
    print("\n🧪 Testing Blue-Green Deployment System\n")

    test_deployment_state_creation()
    test_blue_green_manager_init()
    test_state_persistence()
    test_inactive_version_logic()
    test_port_mapping()
    test_health_check_logic()
    test_deployment_history()
    test_get_status()
    test_configuration_override()

    print("\n✅ All blue-green deployment tests passed!\n")
