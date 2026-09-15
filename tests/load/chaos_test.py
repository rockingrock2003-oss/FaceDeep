"""
Chaos Engineering Utilities for FaceDeep
Run: python -m tests.load.chaos_test
"""
import asyncio
import logging
import random
import time

import httpx

logger = logging.getLogger("facedeep.chaos")

BASE_URL = "http://localhost:8000"


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
    """Hit rate limit to verify it's enforced"""
    async with httpx.AsyncClient(timeout=5.0) as client:
        responses = []
        for i in range(120):
            resp = await client.get(
                f"{BASE_URL}/api/v2/face/all",
                headers={"X-API-Key": "fd_chaos_test_key"},
            )
            responses.append(resp.status_code)
            if resp.status_code == 429:
                logger.info(f"Rate limit hit after {i+1} requests")
                return {"hit_at": i + 1, "enforced": True}

        logger.warning("Rate limit NOT enforced after 120 requests")
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
