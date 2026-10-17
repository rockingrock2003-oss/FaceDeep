from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import boto3
import pytest
import uvicorn
from botocore.config import Config

from facegate.api.app import create_app
from facegate.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"
ACCESS_KEY = "AKIAFACEGATETEST0001"
SECRET_KEY = "test-secret-key-for-sigv4-verification"
API_KEY = "test-api-key"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    """A real FaceGate server on a random port, SigV4 auth enabled."""
    data_dir = tmp_path_factory.mktemp("facegate-data")
    settings = Settings(
        environment="test",
        data_dir=data_dir,
        auth_mode="sigv4",
        credentials=f"{ACCESS_KEY}:{SECRET_KEY}",
        admin_token="admin-test-token",
        api_keys="test-api-key",
        # LFW photos are re-compressed press photos: keep liveness in report
        # mode for the protocol tests; it is tested separately.
        passive_liveness_on_search="report",
        passive_liveness_on_index="report",
    )
    port = _free_port()
    config = uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.time() + 60
    while not srv.started:
        if time.time() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield {"url": f"http://127.0.0.1:{port}", "settings": settings}
    srv.should_exit = True
    thread.join(timeout=10)


def make_client(url: str, key: str = ACCESS_KEY, secret: str = SECRET_KEY):
    return boto3.client(
        "rekognition",
        endpoint_url=url,
        region_name="us-east-1",
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        config=Config(retries={"max_attempts": 1}),
    )


@pytest.fixture(scope="session")
def rek(server):
    return make_client(server["url"])


def image(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()
