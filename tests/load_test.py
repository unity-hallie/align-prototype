#!/usr/bin/env python3
"""
Load test for align-prototype: Simulates 100 concurrent users
Tests key endpoints under load and reports metrics
"""

import concurrent.futures
import requests
import time
import json
from collections import defaultdict
from typing import List, Dict
import statistics

BASE_URL = "http://localhost:5004"

# Endpoints to test (weighted by typical user behavior)
TEST_ENDPOINTS = [
    ("GET", "/", 40),  # Landing page
    ("GET", "/health", 10),  # Health check
    ("GET", "/designer", 15),  # Designer page
    ("GET", "/designer/prototype", 10),  # Prototype page
    ("POST", "/design/improve_outcomes", 5),  # Main workflow
    ("GET", "/settings", 10),  # Settings page
    ("GET", "/about", 5),  # About page
]

class LoadTestResult:
    def __init__(self):
        self.response_times: List[float] = []
        self.status_codes: Dict[int, int] = defaultdict(int)
        self.errors: List[str] = []
        self.successful_requests = 0
        self.failed_requests = 0
        self.start_time = None
        self.end_time = None

    def add_response(self, response_time: float, status_code: int):
        self.response_times.append(response_time)
        self.status_codes[status_code] += 1
        if 200 <= status_code < 300:
            self.successful_requests += 1
        else:
            self.failed_requests += 1

    def add_error(self, error: str):
        self.errors.append(error)
        self.failed_requests += 1

    def get_report(self) -> Dict:
        if not self.response_times:
            return {"error": "No successful requests completed"}

        duration = (self.end_time - self.start_time) if self.end_time and self.start_time else 0
        total_requests = self.successful_requests + self.failed_requests

        return {
            "summary": {
                "total_requests": total_requests,
                "successful": self.successful_requests,
                "failed": self.failed_requests,
                "error_rate_percent": (self.failed_requests / total_requests * 100) if total_requests > 0 else 0,
                "duration_seconds": duration,
                "requests_per_second": total_requests / duration if duration > 0 else 0,
            },
            "response_times": {
                "min_ms": min(self.response_times) * 1000,
                "max_ms": max(self.response_times) * 1000,
                "mean_ms": statistics.mean(self.response_times) * 1000,
                "median_ms": statistics.median(self.response_times) * 1000,
                "p95_ms": sorted(self.response_times)[int(len(self.response_times) * 0.95)] * 1000 if len(self.response_times) > 1 else 0,
                "p99_ms": sorted(self.response_times)[int(len(self.response_times) * 0.99)] * 1000 if len(self.response_times) > 1 else 0,
            },
            "status_codes": dict(self.status_codes),
            "errors": self.errors[:10] if self.errors else [],
        }


def make_request(endpoint_data: tuple) -> tuple:
    """Make a single HTTP request and return timing data"""
    method, path, _ = endpoint_data
    full_url = f"{BASE_URL}{path}"

    try:
        start = time.time()
        if method == "GET":
            response = requests.get(full_url, timeout=30)
        elif method == "POST":
            response = requests.post(full_url, json={}, timeout=30)
        else:
            return None

        elapsed = time.time() - start
        return (elapsed, response.status_code, None)
    except Exception as e:
        return (None, None, str(e))


def run_load_test(num_workers: int = 100, requests_per_worker: int = 10) -> LoadTestResult:
    """
    Run load test with concurrent users

    Args:
        num_workers: Number of concurrent users (default 100)
        requests_per_worker: Requests per user (default 10)
    """
    result = LoadTestResult()
    total_requests = num_workers * requests_per_worker

    print(f"🚀 Starting load test...")
    print(f"   Concurrent users: {num_workers}")
    print(f"   Requests per user: {requests_per_worker}")
    print(f"   Total requests: {total_requests}")
    print(f"   Target: {BASE_URL}\n")

    result.start_time = time.time()

    # Create test tasks
    tasks = []
    for _ in range(total_requests):
        # Select endpoint based on weights
        endpoint = select_weighted_endpoint()
        tasks.append(endpoint)

    # Execute with thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(make_request, task) for task in tasks]

        completed = 0
        for future in concurrent.futures.as_completed(futures):
            try:
                response_time, status_code, error = future.result()
                if error:
                    result.add_error(error)
                else:
                    result.add_response(response_time, status_code)

                completed += 1
                if completed % 100 == 0:
                    print(f"   Progress: {completed}/{total_requests} requests completed")
            except Exception as e:
                result.add_error(str(e))
                completed += 1

    result.end_time = time.time()
    return result


def select_weighted_endpoint():
    """Select endpoint based on weighted distribution"""
    import random

    total_weight = sum(weight for _, _, weight in TEST_ENDPOINTS)
    choice = random.uniform(0, total_weight)
    current = 0

    for method, path, weight in TEST_ENDPOINTS:
        current += weight
        if choice <= current:
            return (method, path, weight)

    return TEST_ENDPOINTS[0]


def print_report(result: LoadTestResult):
    """Pretty-print the load test report"""
    report = result.get_report()

    if "error" in report:
        print(f"\n❌ Test failed: {report['error']}")
        return

    summary = report["summary"]
    times = report["response_times"]

    print("\n" + "="*60)
    print("📊 LOAD TEST RESULTS")
    print("="*60)

    # Summary
    print(f"\n📈 Summary:")
    print(f"   Total requests: {summary['total_requests']}")
    print(f"   Successful: {summary['successful']} ✓")
    print(f"   Failed: {summary['failed']} ✗")
    print(f"   Error rate: {summary['error_rate_percent']:.2f}%")
    print(f"   Duration: {summary['duration_seconds']:.2f}s")
    print(f"   Throughput: {summary['requests_per_second']:.2f} req/s")

    # Response times
    print(f"\n⏱️  Response Times (ms):")
    print(f"   Min: {times['min_ms']:.2f}")
    print(f"   Mean: {times['mean_ms']:.2f}")
    print(f"   Median: {times['median_ms']:.2f}")
    print(f"   P95: {times['p95_ms']:.2f}")
    print(f"   P99: {times['p99_ms']:.2f}")
    print(f"   Max: {times['max_ms']:.2f}")

    # Status codes
    if report["status_codes"]:
        print(f"\n📋 Status Codes:")
        for code, count in sorted(report["status_codes"].items()):
            pct = (count / summary['total_requests']) * 100
            print(f"   {code}: {count} ({pct:.1f}%)")

    # Pass/Fail
    print(f"\n{'✅ PASS' if summary['error_rate_percent'] < 5 else '⚠️  WARNING' if summary['error_rate_percent'] < 10 else '❌ FAIL'}")
    print("="*60 + "\n")

    return report


if __name__ == "__main__":
    import sys

    # Check if server is running
    try:
        requests.get(f"{BASE_URL}/health", timeout=5)
    except Exception as e:
        print(f"❌ Server not running at {BASE_URL}")
        print(f"   Error: {e}")
        sys.exit(1)

    # Run load test
    try:
        result = run_load_test(num_workers=100, requests_per_worker=10)
        report = print_report(result)

        # Save report
        output_file = "/tmp/load_test_report.json"
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)
        print(f"📁 Report saved to: {output_file}")

    except KeyboardInterrupt:
        print("\n⚠️  Load test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Load test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
