"""Command-line entrypoint for the FanPulse weekly digest job."""

import argparse


def main() -> None:
    """Run the scheduled digest workflow without requiring Streamlit."""
    from weekly_digest_job import run_weekly_digest_job

    parser = argparse.ArgumentParser(description="Run the FanPulse weekly digest job.")
    parser.add_argument("--db-path", default=None, help="Path to the FanPulse SQLite DB.")
    args = parser.parse_args()
    print(run_weekly_digest_job(args.db_path))


if __name__ == "__main__":
    main()
