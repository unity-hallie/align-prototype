#!/usr/bin/env python3
"""
Traffic Router: Reverse proxy that routes main port 5004 to active blue-green version.

This module provides a reverse proxy that:
1. Listens on port 5004 (public interface)
2. Reads blue-green state to determine active version (5005 or 5006)
3. Proxies all requests to the active version
4. Handles health checks and connection pooling
5. Provides metrics/debugging endpoints
"""

import json
import os
import sys
import time
import logging
import threading
import traceback
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class RouterConfig:
    """Traffic router configuration."""
    main_port: int = 5004
    state_file: str = ".local_context/bg_state.json"
    read_timeout: int = 30
    connection_timeout: int = 5
    health_check_interval: int = 5
    metrics_enabled: bool = True


class RouterMetrics:
    """Thread-safe metrics collection for router."""

    def __init__(self):
        self.lock = threading.Lock()
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.bytes_proxied = 0
        self.request_times = []
        self.version_requests = {"blue": 0, "green": 0}

    def record_request(self, success: bool, bytes_sent: int, elapsed_time: float, version: str):
        """Record request metrics."""
        with self.lock:
            self.total_requests += 1
            if success:
                self.successful_requests += 1
            else:
                self.failed_requests += 1
            self.bytes_proxied += bytes_sent
            self.request_times.append(elapsed_time)
            self.version_requests[version] = self.version_requests.get(version, 0) + 1

    def get_stats(self) -> Dict[str, Any]:
        """Get current metrics."""
        with self.lock:
            avg_time = (sum(self.request_times) / len(self.request_times) if self.request_times else 0)
            return {
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "success_rate": (
                    self.successful_requests / self.total_requests * 100
                    if self.total_requests > 0 else 0
                ),
                "bytes_proxied": self.bytes_proxied,
                "avg_request_time_ms": avg_time * 1000,
                "version_requests": self.version_requests
            }


class TrafficRouter:
    """Reverse proxy router for blue-green deployments."""

    def __init__(self, config: RouterConfig = None):
        self.config = config or RouterConfig()
        self.metrics = RouterMetrics() if self.config.metrics_enabled else None
        self.state_cache = None
        self.last_state_read = 0

    def get_active_port(self) -> Optional[int]:
        """Get port of active blue-green version."""
        try:
            state = self._read_state()
            if not state:
                return None

            active_version = state.get("active_version")
            if active_version == "blue":
                return state.get("blue_port", 5005)
            elif active_version == "green":
                return state.get("green_port", 5006)
            return None
        except Exception as e:
            logger.error(f"Error reading active port: {e}")
            return None

    def _read_state(self) -> Optional[Dict[str, Any]]:
        """Read and cache blue-green state."""
        try:
            state_path = Path(self.config.state_file)
            if not state_path.exists():
                return None

            # Cache state for 1 second to reduce file I/O
            now = time.time()
            if self.state_cache and (now - self.last_state_read) < 1:
                return self.state_cache

            with open(state_path, 'r') as f:
                self.state_cache = json.load(f)
                self.last_state_read = now
                return self.state_cache
        except Exception as e:
            logger.error(f"Error reading state file: {e}")
            return None

    def proxy_request(
        self,
        method: str,
        path: str,
        headers: Dict[str, str],
        body: Optional[bytes] = None
    ) -> tuple[int, Dict[str, str], bytes]:
        """
        Proxy request to active backend version.

        Args:
            method: HTTP method (GET, POST, etc)
            path: Request path
            headers: Request headers
            body: Request body

        Returns:
            (status_code, response_headers, response_body)
        """
        start_time = time.time()
        active_port = self.get_active_port()

        if not active_port:
            logger.warning("No active version available")
            return 503, {"Content-Type": "text/plain"}, b"No active backend available"

        try:
            # Build backend URL
            url = f"http://localhost:{active_port}{path}"

            # Prepare headers
            req_headers = dict(headers)
            original_host = req_headers.pop("Host", "localhost:5004")  # Remove host header
            req_headers["X-Forwarded-For"] = "127.0.0.1"
            req_headers["X-Forwarded-Proto"] = "http"
            req_headers["X-Forwarded-Host"] = original_host  # ProxyFix needs this!

            # Create request
            req = urllib.request.Request(
                url,
                data=body,
                headers=req_headers,
                method=method
            )

            # Execute request with timeout
            response = urllib.request.urlopen(req, timeout=self.config.read_timeout)
            response_body = response.read()
            response_headers = dict(response.headers)

            elapsed = time.time() - start_time
            version = "blue" if active_port == 5005 else "green"

            if self.metrics:
                self.metrics.record_request(True, len(response_body), elapsed, version)

            logger.info(
                f"✅ Proxied {method} {path} -> {version}:{active_port} "
                f"({response.status}) {elapsed:.2f}s"
            )

            return response.status, response_headers, response_body

        except urllib.error.HTTPError as e:
            elapsed = time.time() - start_time
            version = "blue" if active_port == 5005 else "green"

            if self.metrics:
                self.metrics.record_request(False, 0, elapsed, version)

            logger.error(f"❌ Backend error: {e.code} from {version}:{active_port}")
            return e.code, {"Content-Type": "text/plain"}, e.read()

        except Exception as e:
            elapsed = time.time() - start_time
            version = "blue" if active_port == 5005 else "green"

            if self.metrics:
                self.metrics.record_request(False, 0, elapsed, version)

            logger.error(f"❌ Proxy error: {e}\n{traceback.format_exc()}")
            return 502, {"Content-Type": "text/plain"}, b"Bad gateway"


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Threaded HTTP server."""
    daemon_threads = True


class RouterHandler(BaseHTTPRequestHandler):
    """HTTP request handler for traffic router."""

    # Class variable to share router instance
    router = None

    def do_GET(self):
        self._handle_request("GET", None)

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else None
        self._handle_request("POST", body)

    def do_PUT(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else None
        self._handle_request("PUT", body)

    def do_DELETE(self):
        self._handle_request("DELETE", None)

    def do_HEAD(self):
        self._handle_request("HEAD", None)

    def _handle_request(self, method: str, body: Optional[bytes]):
        """Handle HTTP request by proxying to backend."""
        # Special endpoints
        if self.path == "/__router_health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            active_port = self.router.get_active_port()
            health = {
                "status": "healthy" if active_port else "unhealthy",
                "active_port": active_port,
                "active_version": "blue" if active_port == 5005 else "green" if active_port == 5006 else None
            }
            self.wfile.write(json.dumps(health).encode())
            return

        if self.path == "/__router_metrics":
            if not self.router.metrics:
                self.send_response(404)
                self.end_headers()
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            stats = self.router.metrics.get_stats()
            self.wfile.write(json.dumps(stats).encode())
            return

        # Proxy to backend
        headers = dict(self.headers)
        status, response_headers, response_body = self.router.proxy_request(
            method, self.path, headers, body
        )

        self.send_response(status)
        for header, value in response_headers.items():
            self.send_header(header, value)
        self.end_headers()

        if response_body:
            self.wfile.write(response_body)

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


def start_router(port: int = 5004, config: RouterConfig = None):
    """Start traffic router server."""
    if config is None:
        config = RouterConfig(main_port=port)

    router = TrafficRouter(config)
    RouterHandler.router = router

    server = ThreadedHTTPServer(("127.0.0.1", port), RouterHandler)
    logger.info(f"🌐 Traffic router starting on port {port}")
    logger.info(f"   Proxying to active blue-green version")
    logger.info(f"   Health: http://127.0.0.1:{port}/__router_health")
    logger.info(f"   Metrics: http://127.0.0.1:{port}/__router_metrics")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down router...")
        server.shutdown()


if __name__ == "__main__":
    start_router()
