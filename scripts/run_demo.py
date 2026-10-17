"""Start the full demo: FaceGate (port 8000) + attendance kiosk (port 8443, HTTPS).

    python scripts/run_demo.py

Then open https://<this-machine-ip>:8443 on an iPad/iPhone on the same Wi-Fi
(accept the self-signed certificate warning once), or https://localhost:8443
on this machine.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.gen_cert import local_ips, make_cert  # noqa: E402


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--debug-probes",
        action="store_true",
        help="save every check-in image + scores to data/demo/debug-probes (biometric data: delete when done)",
    )
    ap.add_argument("--password", help="require this password to open the kiosk (use when sharing it on the internet)")
    args = ap.parse_args()
    env_file = ROOT / "data" / "demo" / "credentials.env"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    if not env_file.exists():
        # Demo access key / secret shared by FaceGate and the attendance app,
        # exactly like an IAM access key used against AWS.
        env_file.write_text(f"AKIAFACEGATEDEMO0001\n{secrets.token_urlsafe(30)}\n")
    key_id, secret = env_file.read_text().split()
    cert, key = make_cert(ROOT / "data" / "certs")

    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(ROOT),
            "FACEGATE_CREDENTIALS": f"{key_id}:{secret}",
            "FACEGATE_DATA_DIR": str(ROOT / "data" / "demo" / "facegate"),
            "FACEGATE_ADMIN_TOKEN": env.get("FACEGATE_ADMIN_TOKEN", "demo-admin"),
            "REKOGNITION_ENDPOINT": "http://127.0.0.1:8000",
            "AWS_ACCESS_KEY_ID": key_id,
            "AWS_SECRET_ACCESS_KEY": secret,
        }
    )
    if args.password:
        env["DEMO_PASSWORD"] = args.password
        print("Kiosk is password protected (any username)")
    if args.debug_probes:
        env["FACEGATE_DEBUG_PROBE_DIR"] = str(ROOT / "data" / "demo" / "debug-probes")
        print(f"Saving check-in images and scores to {env['FACEGATE_DEBUG_PROBE_DIR']}")
    py = sys.executable
    procs = [subprocess.Popen([py, "-m", "facegate", "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT, env=env)]
    deadline = time.time() + 90
    while True:
        try:
            if httpx.get("http://127.0.0.1:8000/health", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        if time.time() > deadline or procs[0].poll() is not None:
            print("FaceGate failed to start")
            procs[0].terminate()
            sys.exit(1)
        time.sleep(0.5)
    procs.append(
        subprocess.Popen(
            [py, "-m", "demo.attendance_backend", "--port", "8443", "--ssl-certfile", str(cert), "--ssl-keyfile", str(key)],
            cwd=ROOT,
            env=env,
        )
    )
    print("\n" + "=" * 64)
    print(" FaceGate:        http://127.0.0.1:8000/health")
    print(" Kiosk (laptop):  https://localhost:8443")
    for ip in local_ips():
        if ip != "127.0.0.1":
            print(f" Kiosk (iPad):    https://{ip}:8443")
    print(" Enrol:           /enroll     Dashboard: /dashboard")
    print("=" * 64 + "\nCtrl+C to stop\n")
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
