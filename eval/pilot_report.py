"""Score a pilot session recorded with the kiosk's pilot mode (?pilot=1).

Every attempt in the attendance log carries a test label (genuine, stranger or
an attack type) and the participant's employee ID. This prints, per label and
liveness mode:

* genuine   - correct check-ins, genuine users rejected as spoofs (BPCER),
              wrong-person check-ins, other failures
* stranger  - people who are not enrolled, let in anyway
* attacks   - attacks accepted (APCER), and attacks accepted *as the victim*

with a 95% upper confidence bound, because zero failures in 30 attempts only
shows the true rate is probably below 10%, not that it is zero.

Usage:
    python -m eval.pilot_report                       # all labelled attempts
    python -m eval.pilot_report --since "2026-10-20 09:00"
"""

from __future__ import annotations

import argparse
import math
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "demo" / "attendance.db"


def upper95(k: int, n: int) -> float:
    """One-sided 95% Clopper-Pearson upper bound for a rate of k in n."""
    if n == 0:
        return float("nan")
    if k >= n:
        return 1.0

    def cdf(p: float) -> float:  # P(X <= k) for Binomial(n, p)
        return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))

    lo, hi = k / n, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if cdf(mid) > 0.05:
            lo = mid
        else:
            hi = mid
    return hi


def pct(k: int, n: int) -> str:
    return f"{k}/{n} ({k / n * 100:.1f}%, <= {upper95(k, n) * 100:.1f}%)" if n else "-"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--since", help='only attempts after this local time, e.g. "2026-10-20 09:00"')
    ap.add_argument("--out", type=Path, default=Path("reports/pilot_report.md"))
    args = ap.parse_args()

    db = sqlite3.connect(str(args.db))
    db.row_factory = sqlite3.Row
    q = "SELECT * FROM attendance WHERE test_label IS NOT NULL"
    params: tuple = ()
    if args.since:
        q += " AND ts >= ?"
        params = (datetime.strptime(args.since, "%Y-%m-%d %H:%M").timestamp(),)
    rows = db.execute(q + " ORDER BY ts", params).fetchall()
    if not rows:
        raise SystemExit("No labelled attempts found. Open the kiosk with ?pilot=1 and pick a label before each attempt.")

    # An automatic retry is logged as a second row with the same attempt_id;
    # score each attempt by its final row.
    cols = rows[0].keys()
    final: dict[str, sqlite3.Row] = {}
    for r in rows:
        key = r["attempt_id"] if "attempt_id" in cols and r["attempt_id"] else f"row-{r['id']}"
        final[key] = r
    rows = sorted(final.values(), key=lambda r: r["ts"])

    groups: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        groups[(r["test_label"], r["mode"] or "?")].append(r)

    lines = [
        "# Pilot liveness and recognition results",
        "",
        f"{len(rows)} labelled attempts, {len({r['participant'] for r in rows})} participants, "
        f"{datetime.fromtimestamp(rows[0]['ts']):%Y-%m-%d %H:%M} to {datetime.fromtimestamp(rows[-1]['ts']):%Y-%m-%d %H:%M}.",
        "Rates show count, percentage, and the 95% upper bound on the true rate.",
        "",
        "## Genuine users",
        "",
        "| Mode | Attempts | Correct check-in | Rejected as spoof (BPCER) | Wrong person | Not recognised / no face |",
        "|---|---|---|---|---|---|",
    ]
    for (label, mode), rs in sorted(groups.items()):
        if label != "genuine":
            continue
        n = len(rs)
        ok = sum(1 for r in rs if r["result"] == "present" and r["employee_id"] == r["participant"])
        spoof = sum(1 for r in rs if r["result"] == "spoof")
        wrong = sum(1 for r in rs if r["result"] == "present" and r["employee_id"] != r["participant"])
        other = n - ok - spoof - wrong
        lines.append(f"| {mode} | {n} | {pct(ok, n)} | {pct(spoof, n)} | {pct(wrong, n)} | {pct(other, n)} |")

    lines += [
        "",
        "## Strangers (not enrolled)",
        "",
        "| Mode | Attempts | Let in |",
        "|---|---|---|",
    ]
    for (label, mode), rs in sorted(groups.items()):
        if label == "stranger":
            n = len(rs)
            lines.append(f"| {mode} | {n} | {pct(sum(1 for r in rs if r['result'] == 'present'), n)} |")

    lines += [
        "",
        "## Attacks",
        "",
        "| Attack | Mode | Attempts | Accepted (APCER) | Accepted as the victim | Stopped by liveness |",
        "|---|---|---|---|---|---|",
    ]
    for (label, mode), rs in sorted(groups.items()):
        if label in ("genuine", "stranger"):
            continue
        n = len(rs)
        acc = sum(1 for r in rs if r["result"] == "present")
        as_victim = sum(1 for r in rs if r["result"] == "present" and r["employee_id"] == r["participant"])
        stopped = sum(1 for r in rs if r["result"] == "spoof")
        lines.append(f"| {label} | {mode} | {n} | {pct(acc, n)} | {pct(as_victim, n)} | {pct(stopped, n)} |")

    text = "\n".join(lines) + "\n"
    print(text)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"written to {args.out}")


if __name__ == "__main__":
    main()
