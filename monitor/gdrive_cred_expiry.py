"""Auto-expire Google Drive credentials after a set lifetime (default 50h).

Deletes the OAuth credential files once the lifetime has elapsed, so a leaked
or forgotten credentials.json / token.json doesn't linger.

Usage
-----
    python gdrive_cred_expiry.py            # arm (if needed) + check & delete if expired
    python gdrive_cred_expiry.py --check    # report status only, never delete
    python gdrive_cred_expiry.py --hours 24 # override lifetime (hours)
    python gdrive_cred_expiry.py --now      # delete immediately (skip waiting)
    python gdrive_cred_expiry.py --disarm   # forget the timer (keeps files)

Schedule it (e.g. Task Scheduler) to run hourly so deletion actually fires.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
CRED_DIR = HERE / "module" / "apis" / "google"
MARKER = CRED_DIR / ".cred_expiry.json"

# Files removed once expired.
TARGETS = [CRED_DIR / "credentials.json", CRED_DIR / "token.json"]

DEFAULT_HOURS = 50


def _load_marker():
    if MARKER.exists():
        try:
            return json.loads(MARKER.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _save_marker(armed_at: float, hours: float):
    CRED_DIR.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(
        json.dumps({"armed_at": armed_at, "hours": hours}, indent=2),
        encoding="utf-8",
    )


def _fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def arm(hours: float):
    """Start the countdown if not already running."""
    m = _load_marker()
    if m:
        return m
    now = time.time()
    _save_marker(now, hours)
    return {"armed_at": now, "hours": hours}


def delete_targets():
    removed = []
    for p in TARGETS:
        if p.exists():
            try:
                p.unlink()
                removed.append(p.name)
            except Exception as e:  # pragma: no cover
                print(f"[!] could not delete {p}: {e}")
    if MARKER.exists():
        try:
            MARKER.unlink()
        except Exception:
            pass
    return removed


def main(argv=None):
    ap = argparse.ArgumentParser(description="Expire Google Drive credentials.")
    ap.add_argument("--hours", type=float, default=DEFAULT_HOURS)
    ap.add_argument("--check", action="store_true", help="report only, never delete")
    ap.add_argument("--now", action="store_true", help="delete immediately")
    ap.add_argument("--disarm", action="store_true", help="remove the timer, keep files")
    args = ap.parse_args(argv)

    if args.disarm:
        if MARKER.exists():
            MARKER.unlink()
        print("[i] timer disarmed; credential files left in place")
        return 0

    if args.now:
        removed = delete_targets()
        print(f"[+] deleted: {removed or 'nothing'}")
        return 0

    m = _load_marker()
    if not m:
        m = arm(args.hours)
        print(f"[i] armed at {_fmt(m['armed_at'])} (lifetime {m['hours']:g}h)")

    deadline = m["armed_at"] + m["hours"] * 3600.0
    remaining = deadline - time.time()

    if remaining > 0:
        print(
            f"[i] expires {_fmt(deadline)} "
            f"({remaining/3600:.2f}h remaining)"
        )
        return 0

    if args.check:
        print(f"[!] EXPIRED at {_fmt(deadline)} - run without --check to delete")
        return 0

    removed = delete_targets()
    print(f"[+] expired -> deleted: {removed or 'nothing (already gone)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
