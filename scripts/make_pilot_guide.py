"""Fill the participant guide with the current kiosk link and password, then
print it to PDF with Microsoft Edge (headless).

    python scripts/make_pilot_guide.py

Reads data/demo/tunnel-url.txt and data/demo/tunnel-password.txt (written when
the tunnel and demo are started) unless --link / --password are given. The
filled-in HTML and PDF contain the password, so they are written outside git:
data/demo/pilot-guide.html and FaceGate_Pilot_Test_Guide.pdf (git-ignored).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "docs" / "pilot" / "FaceGate_Pilot_Test_Guide.html"
EDGE_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--link", help="kiosk base URL, e.g. https://xyz.trycloudflare.com")
    ap.add_argument("--password")
    ap.add_argument("--out", type=Path, default=ROOT / "FaceGate_Pilot_Test_Guide.pdf")
    args = ap.parse_args()

    link = (args.link or (ROOT / "data/demo/tunnel-url.txt").read_text()).strip().rstrip("/")
    password = (args.password or (ROOT / "data/demo/tunnel-password.txt").read_text()).strip()
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("{{KIOSK_LINK}}", f"{link}/?pilot=1").replace("{{PASSWORD}}", password)
    filled = ROOT / "data" / "demo" / "pilot-guide.html"
    filled.parent.mkdir(parents=True, exist_ok=True)
    filled.write_text(html, encoding="utf-8")

    edge = next((p for p in EDGE_CANDIDATES if p.exists()), None) or shutil.which("msedge")
    if not edge:
        raise SystemExit(f"Microsoft Edge not found; open {filled} in a browser and print it to PDF.")
    tmp_pdf = ROOT / "data" / "demo" / "pilot-guide.pdf"
    tmp_pdf.unlink(missing_ok=True)
    subprocess.run(
        [str(edge), "--headless=new", "--disable-gpu", "--no-first-run",
         f"--user-data-dir={ROOT / 'data' / 'demo' / 'edge-print-profile'}",
         "--no-pdf-header-footer", f"--print-to-pdf={tmp_pdf}", filled.as_uri()],
        check=False,
    )
    # Edge's launcher can return before the PDF is written.
    for _ in range(60):
        if tmp_pdf.exists() and tmp_pdf.stat().st_size > 0:
            break
        time.sleep(0.5)
    time.sleep(1)
    shutil.copy(tmp_pdf, args.out)
    print(f"guide written to {args.out} (link {link}/?pilot=1)")


if __name__ == "__main__":
    main()
