import sqlite3

import pytest

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


def test_load_enrolled_users_filters_to_whatsapp_ready_profiles(tmp_path):
    db_path = tmp_path / "fanpulse-test.db"
    db = FanPulseDB(str(db_path))

    eligible_id = db.save_user_preferences(
        UserProfile(
            name="Ready Fan",
            phone_number="+14155550123",
            whatsapp_consent=True,
            sports=["basketball"],
        )
    )
    db.save_user_preferences(
        UserProfile(
            name="No Consent",
            phone_number="+14155550124",
            whatsapp_consent=False,
        )
    )
    db.save_user_preferences(
        UserProfile(
            name="No Phone",
            phone_number="",
            whatsapp_consent=True,
        )
    )

    enrolled_users = db.load_enrolled_users()

    assert [user.user_id for user in enrolled_users] == [str(eligible_id)]
    assert enrolled_users[0].phone_number == "+14155550123"
    assert enrolled_users[0].whatsapp_consent is True


def test_database_enforces_foreign_keys(tmp_path):
    db_path = tmp_path / "fanpulse-test.db"
    db = FanPulseDB(str(db_path))
    db.initialize()

    with db._connect() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into tool_runs (
                    user_id, tool_name, success, payload_json
                )
                values (?, ?, ?, ?)
                """,
                (999, "sqlite.save_state", 1, "{}"),
            )
