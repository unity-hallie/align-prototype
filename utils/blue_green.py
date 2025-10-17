#!/usr/bin/env python3
"""
Blue-Green Deployment Manager

Enables zero-downtime deployments by:
1. Running two versions (Blue/Green) simultaneously
2. Health-checking both versions
3. Switching traffic atomically
4. Providing instant rollback capability
"""

import json
import time
import subprocess
import signal
import os
import sys
import requests
from pathlib import Path
from typing import Optional, Dict, Literal
from dataclasses import dataclass, asdict
from datetime import datetime
import threading


@dataclass
class DeploymentState:
    """Current state of blue-green deployment."""
    active_version: Literal["blue", "green"]
    blue_port: int
    green_port: int
    blue_pid: Optional[int] = None
    green_pid: Optional[int] = None
    blue_healthy: bool = False
    green_healthy: bool = False
    last_switch: Optional[str] = None
    last_check: Optional[str] = None
    deployment_history: list = None

    def __post_init__(self):
        if self.deployment_history is None:
            self.deployment_history = []

    def to_dict(self):
        return asdict(self)


class BlueGreenManager:
    """Manages blue-green deployments with health checks and traffic switching."""

    def __init__(self, app_script: str, blue_port: int = 5005, green_port: int = 5006,
                 state_file: Optional[Path] = None):
        """
        Initialize blue-green manager.

        Args:
            app_script: Path to Flask app.py file
            blue_port: Port for blue version (default 5005)
            green_port: Port for green version (default 5006)
            state_file: Path to store deployment state (default .local_context/bg_state.json)
        """
        self.app_script = Path(app_script)
        self.blue_port = blue_port
        self.green_port = green_port
        self.state_file = state_file or (self.app_script.parent / ".local_context" / "bg_state.json")
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.health_check_url = "/health"
        self.health_check_timeout = 5

        # Load existing state or create new
        self.state = self._load_state() or DeploymentState(
            active_version="blue",
            blue_port=blue_port,
            green_port=green_port
        )

    def _load_state(self) -> Optional[DeploymentState]:
        """Load deployment state from disk."""
        try:
            if self.state_file.exists():
                data = json.loads(self.state_file.read_text())
                return DeploymentState(**data)
        except Exception as e:
            print(f"⚠️ Failed to load state: {e}")
        return None

    def _save_state(self):
        """Persist deployment state to disk."""
        try:
            self.state_file.write_text(json.dumps(self.state.to_dict(), indent=2, default=str))
        except Exception as e:
            print(f"⚠️ Failed to save state: {e}")

    def _get_inactive_version(self) -> Literal["blue", "green"]:
        """Get the version that's not currently active."""
        return "green" if self.state.active_version == "blue" else "blue"

    def _get_port(self, version: Literal["blue", "green"]) -> int:
        """Get port for a version."""
        return self.blue_port if version == "blue" else self.green_port

    def _health_check(self, port: int) -> bool:
        """Check if instance on port is healthy."""
        try:
            url = f"http://localhost:{port}{self.health_check_url}"
            response = requests.get(url, timeout=self.health_check_timeout)
            return response.status_code == 200
        except Exception:
            return False

    def start_instance(self, version: Literal["blue", "green"]) -> Optional[int]:
        """
        Start a Flask instance for the given version.

        Returns:
            PID of started process, or None if failed
        """
        port = self._get_port(version)
        env = os.environ.copy()
        env['PORT'] = str(port)
        env['FLASK_ENV'] = 'production'

        print(f"🚀 Starting {version} version on port {port}...")

        try:
            proc = subprocess.Popen(
                [sys.executable, str(self.app_script)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True  # Create new process group for clean kill
            )

            # Store PID
            if version == "blue":
                self.state.blue_pid = proc.pid
            else:
                self.state.green_pid = proc.pid

            # Wait for health check to pass
            print(f"⏳ Waiting for {version} version to be ready...")
            for attempt in range(30):  # 30 attempts × 1 second = 30 second timeout
                time.sleep(1)
                if self._health_check(port):
                    print(f"✅ {version.upper()} version ready on port {port}")
                    if version == "blue":
                        self.state.blue_healthy = True
                    else:
                        self.state.green_healthy = True
                    self._save_state()
                    return proc.pid

            # Health check failed
            print(f"❌ {version.upper()} version failed health check after 30 seconds")
            self.stop_instance(version)
            return None

        except Exception as e:
            print(f"❌ Failed to start {version}: {e}")
            return None

    def stop_instance(self, version: Literal["blue", "green"]) -> bool:
        """
        Stop a Flask instance for the given version.

        Returns:
            True if stopped successfully, False otherwise
        """
        pid = self.state.blue_pid if version == "blue" else self.state.green_pid

        if not pid:
            print(f"⚠️ No PID for {version} version")
            return False

        print(f"🛑 Stopping {version} version (PID {pid})...")

        try:
            # Kill entire process group (including child processes)
            os.killpg(os.getpgid(pid), signal.SIGTERM)

            # Wait for graceful shutdown
            for attempt in range(10):  # 10 seconds
                time.sleep(1)
                try:
                    os.getpgid(pid)  # Will raise if process gone
                except ProcessLookupError:
                    print(f"✅ {version.upper()} version stopped")
                    if version == "blue":
                        self.state.blue_pid = None
                        self.state.blue_healthy = False
                    else:
                        self.state.green_pid = None
                        self.state.green_healthy = False
                    self._save_state()
                    return True

            # Force kill if still running
            os.killpg(os.getpgid(pid), signal.SIGKILL)
            print(f"✅ {version.upper()} version force-killed")
            if version == "blue":
                self.state.blue_pid = None
                self.state.blue_healthy = False
            else:
                self.state.green_pid = None
                self.state.green_healthy = False
            self._save_state()
            return True

        except ProcessLookupError:
            print(f"✅ {version.upper()} version already stopped")
            if version == "blue":
                self.state.blue_pid = None
                self.state.blue_healthy = False
            else:
                self.state.green_pid = None
                self.state.green_healthy = False
            self._save_state()
            return True
        except Exception as e:
            print(f"⚠️ Error stopping {version}: {e}")
            return False

    def deploy_new_version(self) -> bool:
        """
        Deploy a new version to the inactive slot.

        Process:
        1. Start new version (Green) if Blue is active
        2. Wait for Green to be healthy
        3. Switch traffic to Green
        4. Keep Blue running for rollback

        Returns:
            True if deployment successful, False otherwise
        """
        inactive = self._get_inactive_version()
        active = self.state.active_version

        print(f"\n🔄 Starting blue-green deployment (active: {active}, deploying to: {inactive})")

        # Stop any existing inactive version
        if inactive == "blue" and self.state.blue_pid:
            self.stop_instance("blue")
        elif inactive == "green" and self.state.green_pid:
            self.stop_instance("green")

        # Start new version
        pid = self.start_instance(inactive)
        if not pid:
            print(f"❌ Failed to start {inactive} version")
            return False

        # Verify health check passes
        if not self._health_check(self._get_port(inactive)):
            print(f"❌ {inactive.upper()} version failed health check")
            self.stop_instance(inactive)
            return False

        # Switch traffic
        return self.switch_traffic(inactive)

    def switch_traffic(self, new_active: Literal["blue", "green"]) -> bool:
        """
        Atomically switch traffic to a new version.

        Args:
            new_active: Version to make active ("blue" or "green")

        Returns:
            True if switch successful, False otherwise
        """
        old_active = self.state.active_version

        # Verify target is healthy
        if not self._health_check(self._get_port(new_active)):
            print(f"❌ Cannot switch to {new_active}: version is not healthy")
            return False

        # Atomic state update
        self.state.active_version = new_active
        self.state.last_switch = datetime.utcnow().isoformat() + "Z"

        # Record in history
        self.state.deployment_history.append({
            "timestamp": self.state.last_switch,
            "from": old_active,
            "to": new_active,
            "status": "success"
        })

        self._save_state()

        print(f"✅ Traffic switched: {old_active} → {new_active}")
        print(f"   Active version now on port {self._get_port(new_active)}")
        print(f"   Inactive version ({old_active}) on port {self._get_port(old_active)} (ready for rollback)")

        return True

    def rollback(self) -> bool:
        """
        Rollback to the previous version (instant traffic switch).

        Returns:
            True if rollback successful, False otherwise
        """
        inactive = self._get_inactive_version()

        print(f"\n🔄 Rolling back to {inactive}...")

        # Verify target is still healthy
        if not self._health_check(self._get_port(inactive)):
            print(f"❌ Cannot rollback to {inactive}: version is not healthy")
            return False

        return self.switch_traffic(inactive)

    def get_status(self) -> Dict:
        """Get current deployment status."""
        self.state.last_check = datetime.utcnow().isoformat() + "Z"

        # Update health status
        self.state.blue_healthy = self._health_check(self.blue_port)
        self.state.green_healthy = self._health_check(self.green_port)

        self._save_state()

        return {
            "active_version": self.state.active_version,
            "active_port": self._get_port(self.state.active_version),
            "blue": {
                "port": self.blue_port,
                "pid": self.state.blue_pid,
                "healthy": self.state.blue_healthy,
                "status": "running" if self.state.blue_pid else "stopped"
            },
            "green": {
                "port": self.green_port,
                "pid": self.state.green_pid,
                "healthy": self.state.green_healthy,
                "status": "running" if self.state.green_pid else "stopped"
            },
            "last_switch": self.state.last_switch,
            "last_check": self.state.last_check,
            "history": self.state.deployment_history[-5:]  # Last 5 deployments
        }


def get_blue_green_manager(app_path: Optional[Path] = None) -> BlueGreenManager:
    """Get or create global blue-green manager."""
    if app_path is None:
        app_path = Path(__file__).parent.parent / "app.py"
    return BlueGreenManager(str(app_path))
