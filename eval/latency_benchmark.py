"""End-to-end latency through the real API, measured the way the attendance
backend experiences it: boto3 -> SigV4 -> HTTP -> FaceGate -> response.

1. Creates a collection and enrols N people (default 1,000 - a mid-size
   company) from LFW.
2. Sends check-in requests built like kiosk captures (640x480 JPEG with the
   face filling a large part of the frame), sequentially and concurrently.
3. Reports p50 / p95 / p99 of both the client round trip and the server-side
   processing time (x-facegate-server-ms header).

Usage (FaceGate running, e.g. via scripts/run_demo.py):
    python -m eval.latency_benchmark --endpoint http://127.0.0.1:8000 \
        --key AKIA... --secret ... --lfw data/lfw/lfw
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3
import cv2
from botocore.config import Config


def kiosk_jpeg(path: Path) -> bytes:
    """Turn a 250x250 LFW photo into a 640x480 kiosk-style capture."""
    img = cv2.imread(str(path))
    face = cv2.resize(img, (420, 420), interpolation=cv2.INTER_CUBIC)
    canvas = cv2.copyMakeBorder(face, 30, 30, 110, 110, cv2.BORDER_REFLECT)
    canvas = cv2.resize(canvas, (640, 480))
    ok, buf = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes()


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def summary(xs: list[float]) -> dict:
    return {
        "n": len(xs),
        "p50": round(pct(xs, 50), 1),
        "p95": round(pct(xs, 95), 1),
        "p99": round(pct(xs, 99), 1),
        "mean": round(statistics.mean(xs), 1),
        "max": round(max(xs), 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://127.0.0.1:8000")
    ap.add_argument("--key", required=True)
    ap.add_argument("--secret", required=True)
    ap.add_argument("--lfw", type=Path, default=Path("data/lfw/lfw"))
    ap.add_argument("--enrol", type=int, default=1000)
    ap.add_argument("--requests", type=int, default=200)
    ap.add_argument("--concurrency", type=int, nargs="+", default=[1, 4])
    ap.add_argument("--report", type=Path, default=Path("reports/latency.json"))
    ap.add_argument("--keep", action="store_true", help="keep the benchmark collection")
    args = ap.parse_args()

    client = boto3.client(
        "rekognition",
        endpoint_url=args.endpoint,
        region_name="us-east-1",
        aws_access_key_id=args.key,
        aws_secret_access_key=args.secret,
        config=Config(retries={"max_attempts": 1}, max_pool_connections=32, tcp_keepalive=True),
    )
    rng = random.Random(7)
    people = sorted(p for p in args.lfw.iterdir() if len(list(p.glob("*.jpg"))) >= 2)
    rng.shuffle(people)
    people = people[: args.enrol]
    cid = f"latency-{uuid.uuid4().hex[:8]}"
    client.create_collection(CollectionId=cid)
    print(f"enrolling {len(people)} people into {cid} ...")
    t0 = time.time()
    enrol_ms = []
    probes = []
    for p in people:
        files = sorted(p.glob("*.jpg"))
        t = time.perf_counter()
        client.index_faces(CollectionId=cid, Image={"Bytes": files[0].read_bytes()}, ExternalImageId=p.name, MaxFaces=1, QualityFilter="NONE")
        enrol_ms.append((time.perf_counter() - t) * 1000)
        probes.append((p.name, kiosk_jpeg(files[1])))
    print(f"  done in {time.time() - t0:.0f}s, IndexFaces p50 {pct(enrol_ms, 50):.0f} ms")

    report = {"endpoint": args.endpoint, "enrolled_faces": len(people), "index_faces_ms": summary(enrol_ms), "search": {}}

    def one(item):
        name, jpeg = item
        t = time.perf_counter()
        r = client.search_faces_by_image(CollectionId=cid, Image={"Bytes": jpeg}, MaxFaces=1, FaceMatchThreshold=95)
        rt = (time.perf_counter() - t) * 1000
        server = float(r["ResponseMetadata"]["HTTPHeaders"].get("x-facegate-server-ms", "nan"))
        hit = bool(r["FaceMatches"]) and r["FaceMatches"][0]["Face"].get("ExternalImageId") == name
        return rt, server, hit

    # warm-up
    for item in probes[:5]:
        one(item)
    for conc in args.concurrency:
        batch = [probes[i % len(probes)] for i in range(args.requests)]
        t = time.time()
        with ThreadPoolExecutor(conc) as pool:
            res = list(pool.map(one, batch))
        wall = time.time() - t
        rts, servers, hits = zip(*res)
        report["search"][f"concurrency_{conc}"] = {
            "client_roundtrip_ms": summary(list(rts)),
            "server_processing_ms": summary([s for s in servers if s == s]),
            "throughput_rps": round(len(res) / wall, 1),
            # Probes are 250 px LFW photos upscaled to 640x480, so this is a
            # load signal only; accuracy comes from eval/lfw_benchmark.py.
            "identified_synthetic_probes": round(sum(hits) / len(hits), 4),
        }
        r = report["search"][f"concurrency_{conc}"]
        print(
            f"concurrency {conc}: round trip p50 {r['client_roundtrip_ms']['p50']} / p95 {r['client_roundtrip_ms']['p95']} ms, "
            f"server p50 {r['server_processing_ms']['p50']} ms, {r['throughput_rps']} req/s"
        )
    if not args.keep:
        client.delete_collection(CollectionId=cid)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2))
    print(f"report written to {args.report}")


if __name__ == "__main__":
    main()

