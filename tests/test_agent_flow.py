import sqlite3

from fanpulse_agent.database import FanPulseDB
from fanpulse_agent.models import ToolResult, TraceEntry, UserProfile


def test_database_creates_tables_and_logs_records(tmp_path):
    db_path = tmp_path / "fanpulse-test.db"
    db = FanPulseDB(str(db_path))

    db.initialize()
    user_id = db.save_user_preferences(
        UserProfile(name="Mansoor", phone_number="+14155550123")
    )
    db.log_tool_run(
        user_id,
        ToolResult("sqlite.save_state", True, {"user_id": user_id}, None, None, 1.0),
    )
    db.log_trace(
        user_id,
        TraceEntry(
            step="persist_state",
            message="Saved onboarding state",
            tool_name="sqlite.save_state",
            metadata={"user_id": user_id},
        ),
    )

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("select count(*) from users").fetchone()[0] == 1
        assert connection.execute("select count(*) from tool_runs").fetchone()[0] == 1
        assert connection.execute("select count(*) from agent_trace").fetchone()[0] == 1
