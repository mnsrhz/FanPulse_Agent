"""Scheduled weekly digest runner for enrolled FanPulse users."""

from __future__ import annotations

import argparse
from datetime import date
from typing import Dict, Optional

from fanpulse_agent.agent import FanPulseAgent
from fanpulse_agent.database import FanPulseDB
from fanpulse_agent.models import TraceEntry, UserProfile


def run_weekly_digest_job(
    db_path: Optional[str] = None, run_key: Optional[str] = None
) -> Dict[str, int]:
    """Generate and send weekly digests for WhatsApp-enrolled users."""
    db = FanPulseDB(db_path)
    db.initialize()
    agent = FanPulseAgent(db)
    run_key = run_key or _current_run_key()
    summary = {
        "users_processed": 0,
        "digests_created": 0,
        "sent": 0,
        "failed": 0,
        "skipped": 0,
    }

    for profile in db.load_enrolled_users():
        summary["users_processed"] += 1
        user_id = db.resolve_user_id(profile)
        if db.has_digest_run(user_id, run_key):
            summary["skipped"] += 1
            continue

        try:
            digest = agent.run_weekly_digest_for_profile(profile)
        except Exception as exc:
            summary["failed"] += 1
            _log_failure(db, profile, exc)
            continue

        summary["digests_created"] += 1
        db.mark_latest_digest_run(user_id, run_key)
        if getattr(digest, "sent", False):
            summary["sent"] += 1

    summary["processed"] = summary["users_processed"]
    return summary


def _log_failure(db: FanPulseDB, profile: UserProfile, exc: Exception) -> None:
    try:
        user_id = db.resolve_user_id(profile)
        db.log_trace(
            user_id,
            TraceEntry(
                step="weekly_digest_failed",
                message="Weekly digest job failed for enrolled user.",
                metadata={
                    "profile_name": profile.name,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            ),
        )
    except Exception:
        return


def _current_run_key() -> str:
    iso_year, iso_week, _ = date.today().isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the FanPulse weekly digest job.")
    parser.add_argument("--db-path", default=None, help="Path to the FanPulse SQLite DB.")
    parser.add_argument(
        "--run-key",
        default=None,
        help="Idempotency key for this scheduled period, for example 2026-W25.",
    )
    args = parser.parse_args()
    print(run_weekly_digest_job(args.db_path, run_key=args.run_key))


if __name__ == "__main__":
    main()
