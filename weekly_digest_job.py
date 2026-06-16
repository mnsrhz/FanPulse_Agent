"""Scheduled weekly digest runner for enrolled FanPulse users."""

from __future__ import annotations

import argparse
from typing import Dict, Optional

from fanpulse_agent.agent import FanPulseAgent
from fanpulse_agent.database import FanPulseDB
from fanpulse_agent.models import TraceEntry, UserProfile


def run_weekly_digest_job(db_path: Optional[str] = None) -> Dict[str, int]:
    """Generate and send weekly digests for WhatsApp-enrolled users."""
    db = FanPulseDB(db_path)
    db.initialize()
    agent = FanPulseAgent(db)
    summary = {
        "users_processed": 0,
        "digests_created": 0,
        "sent": 0,
        "failed": 0,
    }

    for profile in db.load_enrolled_users():
        summary["users_processed"] += 1
        try:
            digest = agent.run_weekly_digest_for_profile(profile)
        except Exception as exc:
            summary["failed"] += 1
            _log_failure(db, profile, exc)
            continue

        summary["digests_created"] += 1
        if getattr(digest, "sent", False):
            summary["sent"] += 1

    summary["processed"] = summary["users_processed"]
    return summary


def _log_failure(db: FanPulseDB, profile: UserProfile, exc: Exception) -> None:
    try:
        user_id = int(profile.user_id) if profile.user_id else db.save_user_preferences(profile)
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the FanPulse weekly digest job.")
    parser.add_argument("--db-path", default=None, help="Path to the FanPulse SQLite DB.")
    args = parser.parse_args()
    print(run_weekly_digest_job(args.db_path))


if __name__ == "__main__":
    main()
