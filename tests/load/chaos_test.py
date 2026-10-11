"""
Chaos Engineering Utilities for FaceDeep
Run: python -m tests.load.chaos_test
"""

import asyncio
import logging
import os
import time

import httpx

logger = logging.getLogger("facedeep.chaos")

BASE_URL = os.getenv("FACEDEEP_BASE_URL", "http://localhost:8000").rstrip("/")
CHAOS_API_KEY = os.getenv("FACEDEEP_CHAOS_API_KEY", "")


async def test_latency_injection():
    """Simulate high latency by hitting slow endpoints"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        start = time.time()
        resp = await client.get(f"{BASE_URL}/api/v2/health")
        elapsed = time.time() - start
        logger.info(f"Health check latency: {elapsed:.3f}s (status={resp.status_code})")
        return elapsed


async def test_concurrent_requests(n: int = 50):
    """Send N concurrent requests to test concurrency handling"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        tasks = [client.get(f"{BASE_URL}/api/v2/health") for _ in range(n)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successes = sum(1 for r in results if not isinstance(r, Exception))
        failures = sum(1 for r in results if isinstance(r, Exception))
        logger.info(f"Concurrent test: {successes}/{n} succeeded, {failures} failed")
        return {"successes": successes, "failures": failures}


async def test_rate_limit_enforcement():
    """Verify throttling with a real API key and a rate-limited endpoint."""
    if not CHAOS_API_KEY:
        logger.warning(
            "Skipping rate-limit check: set FACEDEEP_CHAOS_API_KEY to a valid test API key"
        )
        return {"hit_at": None, "enforced": None, "skipped": "missing_api_key"}

    headers = {"X-API-Key": CHAOS_API_KEY}
    async with httpx.AsyncClient(timeout=5.0) as client:
        first = await client.post(
            f"{BASE_URL}/api/v2/face/recognize",
            headers=headers,
        )
        limit_header = first.headers.get("X-RateLimit-Limit-Minute")
        if not limit_header:
            logger.warning("Skipping rate-limit check: rate-limit headers are unavailable")
            return {"hit_at": None, "enforced": None, "skipped": "rate_limiter_unavailable"}

        rpm_limit = int(limit_header)
        if rpm_limit <= 0:
            logger.warning("Skipping rate-limit check: Redis-backed limiter is unavailable")
            return {"hit_at": None, "enforced": None, "skipped": "rate_limiter_unavailable"}
        if rpm_limit > 500:
            logger.warning(
                "Skipping rate-limit check: plan limit %s RPM is too high for a chaos smoke test",
                rpm_limit,
            )
            return {"hit_at": None, "enforced": None, "skipped": "limit_too_high"}

        for request_number in range(2, rpm_limit + 3):
            resp = await client.post(
                f"{BASE_URL}/api/v2/face/recognize",
                headers=headers,
            )
            if resp.status_code == 429:
                logger.info("Rate limit hit after %s requests", request_number)
                return {"hit_at": request_number, "enforced": True}

        logger.warning("Rate limit was not enforced after %s requests", rpm_limit + 2)
        return {"hit_at": None, "enforced": False}


async def test_error_handling():
    """Send malformed requests to test error handling"""
    async with httpx.AsyncClient(timeout=5.0) as client:
        bad_payloads = [
            {"invalid": "payload"},
            "not json",
            b"\x00\x01\x02",
        ]

        for i, payload in enumerate(bad_payloads):
            try:
                resp = await client.post(
                    f"{BASE_URL}/api/v2/face/recognize",
                    content=payload,
                    headers={"Content-Type": "application/json"},
                )
                logger.info(f"Bad payload {i}: status={resp.status_code}")
            except Exception as e:
                logger.error(f"Bad payload {i}: exception={e}")


async def run_all_chaos_tests():
    """Run all chaos tests"""
    logger.info("=== Starting Chaos Engineering Tests ===")

    results = {}
    results["latency"] = await test_latency_injection()
    results["concurrency"] = await test_concurrent_requests(50)
    results["rate_limit"] = await test_rate_limit_enforcement()
    await test_error_handling()

    logger.info("=== Chaos Tests Complete ===")
    logger.info(f"Results: {results}")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_all_chaos_tests())
