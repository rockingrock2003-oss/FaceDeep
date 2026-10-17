"""``python -m facegate`` - run the service."""

from __future__ import annotations

import argparse
import logging

import uvicorn

from facegate.config import get_settings


def main() -> None:
    s = get_settings()
    ap = argparse.ArgumentParser(description="FaceGate - Rekognition-compatible face service")
    ap.add_argument("--host", default=s.host)
    ap.add_argument("--port", type=int, default=s.port)
    ap.add_argument("--ssl-certfile")
    ap.add_argument("--ssl-keyfile")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(
        "facegate.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        ssl_certfile=args.ssl_certfile,
        ssl_keyfile=args.ssl_keyfile,
        log_level="info",
        # One process; requests run in a thread pool. Scale out with more
        # processes/containers behind a load balancer (state is in SQLite +
        # memory, so use one writer per data directory - see docs).
        workers=1,
    )


if __name__ == "__main__":
    main()
