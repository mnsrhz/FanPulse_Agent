import sqlite3

import pytest

from fanpulse_agent.agent import FanPulseAgent
from fanpulse_agent.database import FanPulseDB
from fanpulse_agent.models import ToolResult, TraceEntry, UserProfile
from fanpulse_agent.tools import (
    generate_digest,
    get_next_team_events_thesportsdb,
    normalize_sports_entity,
    rank_events,
    search_team_thesportsdb,
    web_search_event_source,
)


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


def test_mock_tools_return_structured_results():
    normalized = normalize_sports_entity("Lakers")
    team = search_team_thesportsdb("Los Angeles Lakers")
    events = get_next_team_events_thesportsdb(team.data["team_id"])
    athlete = web_search_event_source("Novak Djokovic")
    ranked = rank_events(
        events.data["events"] + athlete.data["events"], UserProfile(name="Mansoor")
    )
    digest = generate_digest(ranked.data["events"], UserProfile(name="Mansoor"))

    assert normalized.success is True
    assert team.data["team_id"] == "lakers"
    assert events.data["events"][0].entity_name == "Los Angeles Lakers"
    assert events.data["events"][0].to_dict()["entity_name"] == "Los Angeles Lakers"
    assert athlete.data["events"][0].entity_name == "Novak Djokovic"
    assert "FanPulse Weekly Digest" in digest.data["digest"].title
    digest_events = digest.data["digest"].to_dict()["events"]
    assert digest_events[0]["entity_name"]
    assert any(event["entity_name"] == "Los Angeles Lakers" for event in digest_events)
    assert all(result.mock for result in [normalized, team, events, athlete, ranked, digest])


def test_agent_runs_sample_flow_with_approval_gates(tmp_path):
    db = FanPulseDB(str(tmp_path / "agent.db"))
    agent = FanPulseAgent(db)
    response = agent.handle_user_message(
        "I am Mansoor. I follow the Lakers, Real Madrid, India cricket, "
        "Novak Djokovic and Max Verstappen. Send my digest every Friday morning "
        "to +14155550123 on WhatsApp."
    )
    assert response.requires_action == "clarify_ambiguity"
    assert "India" in response.message
    response = agent.resolve_ambiguity("India men's national cricket team")
    assert response.requires_action == "confirm_preferences"
    response = agent.confirm_preferences()
    assert response.requires_action == "approve_digest"
    assert response.digest is not None
    assert len(response.digest.events) >= 4
    response = agent.approve_and_send_digest()
    assert response.requires_action == "complete"
    assert response.digest.sent is True


def test_agent_persists_distinct_onboarding_users(tmp_path):
    db_path = tmp_path / "agent.db"
    db = FanPulseDB(str(db_path))

    alice = FanPulseAgent(db)
    response = alice.handle_user_message(
        "I am Alice. I follow the Lakers. Send my digest every Friday morning "
        "to +14155550123 on WhatsApp."
    )
    assert response.requires_action == "confirm_preferences"
    response = alice.confirm_preferences()
    assert response.requires_action == "approve_digest"

    bob = FanPulseAgent(db)
    response = bob.handle_user_message(
        "I am Bob. I follow the 49ers. Send my digest every Friday morning "
        "to +14155550124 on WhatsApp."
    )
    assert response.requires_action == "confirm_preferences"
    response = bob.confirm_preferences()
    assert response.requires_action == "approve_digest"

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "select name, phone_number from users order by id"
        ).fetchall()

    assert rows == [
        ("Alice", "+14155550123"),
        ("Bob", "+14155550124"),
    ]


def test_agent_approval_is_idempotent(tmp_path):
    db_path = tmp_path / "agent.db"
    db = FanPulseDB(str(db_path))
    agent = FanPulseAgent(db)
    response = agent.handle_user_message(
        "I am Mansoor. I follow the Lakers, Real Madrid, India cricket, "
        "Novak Djokovic and Max Verstappen. Send my digest every Friday morning "
        "to +14155550123 on WhatsApp."
    )
    assert response.requires_action == "clarify_ambiguity"
    response = agent.resolve_ambiguity("India men's national cricket team")
    assert response.requires_action == "confirm_preferences"
    response = agent.confirm_preferences()
    assert response.requires_action == "approve_digest"

    first_response = agent.approve_and_send_digest()
    second_response = agent.approve_and_send_digest()

    assert first_response.requires_action == "complete"
    assert second_response.requires_action == "complete"
    assert first_response.digest is not None
    assert second_response.digest is first_response.digest
    with sqlite3.connect(db_path) as connection:
        whatsapp_runs = connection.execute(
            "select count(*) from tool_runs where tool_name = 'whatsapp.send_digest'"
        ).fetchone()[0]
        digest_history_rows = connection.execute(
            "select count(*) from digest_history"
        ).fetchone()[0]

    assert whatsapp_runs == 1
    assert digest_history_rows == 1


def test_weekly_job_runs_for_enrolled_user(tmp_path):
    from weekly_digest_job import run_weekly_digest_job

    db_path = tmp_path / "weekly.db"
    db = FanPulseDB(str(db_path))
    agent = FanPulseAgent(db)
    agent.handle_user_message(
        "I am Mansoor. I follow the Lakers and Real Madrid. Send my digest every Friday morning "
        "to +14155550123 on WhatsApp."
    )
    agent.confirm_preferences()

    summary = run_weekly_digest_job(str(db_path))

    assert summary["users_processed"] == 1
    assert summary["digests_created"] == 1


def test_weekly_job_is_idempotent_for_run_key(tmp_path):
    from weekly_digest_job import run_weekly_digest_job

    db_path = tmp_path / "weekly.db"
    db = FanPulseDB(str(db_path))
    agent = FanPulseAgent(db)
    agent.handle_user_message(
        "I am Mansoor. I follow the Lakers and Real Madrid. Send my digest every Friday morning "
        "to +14155550123 on WhatsApp."
    )
    agent.confirm_preferences()

    first_summary = run_weekly_digest_job(str(db_path), run_key="2026-W25")
    second_summary = run_weekly_digest_job(str(db_path), run_key="2026-W25")

    assert first_summary["digests_created"] == 1
    assert first_summary["sent"] == 1
    assert second_summary["skipped"] == 1
    assert second_summary["digests_created"] == 0
    assert second_summary["sent"] == 0
    with sqlite3.connect(db_path) as connection:
        digest_history_rows = connection.execute(
            "select count(*) from digest_history"
        ).fetchone()[0]
        whatsapp_runs = connection.execute(
            "select count(*) from tool_runs where tool_name = 'whatsapp.send_digest'"
        ).fetchone()[0]

    assert digest_history_rows == 1
    assert whatsapp_runs == 1


def test_weekly_job_logs_failure_for_external_user_id(tmp_path, monkeypatch):
    from weekly_digest_job import run_weekly_digest_job

    db_path = tmp_path / "weekly.db"
    db = FanPulseDB(str(db_path))
    db.save_user_preferences(
        UserProfile(
            user_id="wa-user-123",
            name="WhatsApp Fan",
            phone_number="+14155550123",
            whatsapp_consent=True,
            sports=["basketball"],
        )
    )

    def fail_weekly_digest(self, profile):
        raise RuntimeError("forced weekly failure")

    monkeypatch.setattr(
        FanPulseAgent, "run_weekly_digest_for_profile", fail_weekly_digest
    )

    summary = run_weekly_digest_job(str(db_path))

    assert summary["failed"] == 1
    with sqlite3.connect(db_path) as connection:
        failed_steps = connection.execute(
            "select count(*) from agent_trace where step = 'weekly_digest_failed'"
        ).fetchone()[0]

    assert failed_steps == 1
