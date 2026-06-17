import json
import sqlite3

import pytest

from fanpulse_agent.agent import FanPulseAgent
from fanpulse_agent.agent_planner import AgentPlan, DigestToolPlan
from fanpulse_agent.database import FanPulseDB
from fanpulse_agent.models import Event, ToolResult, TraceEntry, UserProfile
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


def test_rank_events_filters_past_events_from_digest():
    ranked = rank_events(
        [
            Event(
                title="Past tennis result",
                event_type="athlete_update",
                start_time="2020-04-18T13:00:00+01:00",
                entity_name="Novak Djokovic",
                metadata={"sport": "tennis"},
            ),
            Event(
                title="Future tennis match",
                event_type="match",
                start_time="2999-04-18T13:00:00+01:00",
                entity_name="Novak Djokovic",
                metadata={"sport": "tennis"},
            ),
        ],
        UserProfile(name="Mansoor", sports=["tennis"]),
    )

    assert [event.title for event in ranked.data["events"]] == ["Future tennis match"]


def test_mock_event_to_dict_includes_card_shape_fields():
    team = search_team_thesportsdb("Los Angeles Lakers")
    events = get_next_team_events_thesportsdb(team.data["team_id"])

    event_payload = events.data["events"][0].to_dict()

    assert event_payload["sport_icon"] == "🏀"
    assert event_payload["display_time"] == "Fri, Jun 19, 2026 · 7:30 PM PDT"
    assert event_payload["confidence"] == pytest.approx(0.95)
    assert event_payload["mock"] is True
    assert event_payload["incomplete"] is False
    assert event_payload["source_url"] == "https://www.thesportsdb.com/"
    assert event_payload["entity_name"] == "Los Angeles Lakers"


def test_agent_runs_sample_flow_with_approval_gates(tmp_path):
    db = FanPulseDB(str(tmp_path / "agent.db"))
    agent = FanPulseAgent(db)
    response = agent.handle_user_message(
        "I am Mansoor. I follow the Lakers, Real Madrid, India cricket, "
        "Novak Djokovic and Max Verstappen. Send my digest every Friday morning "
        "to +14155550123 on WhatsApp. Use Pacific time."
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


def test_agent_sends_whatsapp_digest_with_card_details(tmp_path, monkeypatch):
    import fanpulse_agent.tools as tools_module

    captured = {}

    def fake_send(phone_number, digest_text):
        captured["phone_number"] = phone_number
        captured["digest_text"] = digest_text
        return ToolResult(
            "whatsapp.send_digest",
            True,
            {
                "phone_number": phone_number,
                "message_preview": digest_text[:160],
                "sent": True,
                "delivery_status": "mocked_for_test",
            },
            "https://business.whatsapp.com/",
            None,
            1.0,
            True,
        )

    monkeypatch.setattr(tools_module, "send_whatsapp_digest", fake_send)
    monkeypatch.setattr("fanpulse_agent.agent.send_whatsapp_digest", fake_send)

    db = FanPulseDB(str(tmp_path / "agent.db"))
    agent = FanPulseAgent(db)
    response = agent.handle_user_message(
        "I am Mansoor. I follow the Lakers. Send my digest every Friday morning "
        "to +14155550123 on WhatsApp. Use Pacific time."
    )
    assert response.requires_action == "confirm_preferences"
    response = agent.confirm_preferences()
    assert response.requires_action == "approve_digest"

    response = agent.approve_and_send_digest()

    assert response.requires_action == "complete"
    text = captured["digest_text"]
    assert len(text) <= 400
    assert text.startswith("FanPulse digest")
    assert "🏀 Los Angeles Lakers vs Golden State Warriors" in text
    assert "Fri, Jun 19, 2026 · 7:30 PM PDT" in text
    assert "https://www.thesportsdb.com/" in text
    assert "League:" not in text
    assert "confidence" not in text


def test_agent_collects_name_and_timezone_before_confirming_preferences(tmp_path):
    db = FanPulseDB(str(tmp_path / "agent.db"))
    agent = FanPulseAgent(db)

    response = agent.handle_user_message(
        "I follow the Lakers and Novak Djokovic. Send my digest every Friday morning "
        "to +14155550123 on WhatsApp."
    )

    assert response.requires_action == "collect_profile_details"
    assert "name" in response.message.lower()
    assert "timezone" in response.message.lower()
    assert [team.name for team in response.profile.teams] == ["Los Angeles Lakers"]

    response = agent.handle_user_message("I'm Mansoor and I am in Pacific time.")

    assert response.requires_action == "confirm_preferences"
    assert response.profile.name == "Mansoor"
    assert response.profile.name_provided is True
    assert response.profile.timezone == "America/Los_Angeles"
    assert response.profile.timezone_provided is True
    assert [team.name for team in response.profile.teams] == ["Los Angeles Lakers"]
    assert [athlete.name for athlete in response.profile.athletes] == ["Novak Djokovic"]


def test_agent_uses_llm_planner_for_profile_followup_message(tmp_path, monkeypatch):
    import fanpulse_agent.agent as agent_module

    db = FanPulseDB(str(tmp_path / "agent.db"))
    agent = FanPulseAgent(db)

    def planned_next_action(**kwargs):
        return AgentPlan(
            next_action="collect_profile_details",
            assistant_message="What should I call you, and what timezone should anchor the digest?",
            reasoning="The profile is missing name and timezone.",
            tool_plan=[],
        )

    monkeypatch.setattr(agent_module, "plan_next_agent_action", planned_next_action)

    response = agent.handle_user_message(
        "I follow the Lakers and Novak Djokovic. Send my digest every Friday morning "
        "to +14155550123 on WhatsApp."
    )

    assert response.requires_action == "collect_profile_details"
    assert response.message == (
        "What should I call you, and what timezone should anchor the digest?"
    )
    assert response.trace[-1].step == "llm_plan_next_action"
    assert response.trace[-1].metadata["next_action"] == "collect_profile_details"


def test_agent_logs_llm_digest_tool_plan_before_tool_execution(tmp_path, monkeypatch):
    import fanpulse_agent.agent as agent_module

    db = FanPulseDB(str(tmp_path / "agent.db"))
    agent = FanPulseAgent(db)

    monkeypatch.setattr(
        agent_module,
        "plan_digest_tool_calls",
        lambda profile: DigestToolPlan(
            tools=[
                "sportsdb.search_team",
                "sportsdb.get_next_team_events",
                "digest.generate",
            ],
            reasoning="Use team schedule tools before generating the digest.",
        ),
    )

    response = agent.handle_user_message(
        "I am Mansoor. I follow the Lakers. Send my digest every Friday morning "
        "to +14155550123 on WhatsApp. Use Pacific time."
    )
    assert response.requires_action == "confirm_preferences"

    response = agent.confirm_preferences()

    assert response.requires_action == "approve_digest"
    plan_trace = next(
        entry for entry in response.trace if entry.step == "llm_plan_tool_calls"
    )
    assert plan_trace.metadata["tools"] == [
        "sportsdb.search_team",
        "sportsdb.get_next_team_events",
        "digest.generate",
    ]


def test_agent_understands_natural_name_timezone_followup(tmp_path):
    db = FanPulseDB(str(tmp_path / "agent.db"))
    agent = FanPulseAgent(db)

    response = agent.handle_user_message(
        "I follow the Lakers. Send the digest to 415-555-0123 on WhatsApp."
    )
    assert response.requires_action == "collect_profile_details"

    response = agent.handle_user_message("Mansoor, California, every 1 hour")

    assert response.requires_action == "confirm_preferences"
    assert response.profile.name == "Mansoor"
    assert response.profile.name_provided is True
    assert response.profile.timezone == "America/Los_Angeles"
    assert response.profile.timezone_provided is True
    assert response.profile.digest_schedule == "Every 1 hour"
    assert response.profile.schedule_provided is True
    assert [team.name for team in response.profile.teams] == ["Los Angeles Lakers"]


def test_agent_collects_frequency_before_confirming_preferences(tmp_path):
    db = FanPulseDB(str(tmp_path / "agent.db"))
    agent = FanPulseAgent(db)

    response = agent.handle_user_message(
        "I am Mansoor. I follow the Lakers. Send it to +14155550123 on WhatsApp. Use Pacific time."
    )

    assert response.requires_action == "collect_profile_details"
    assert "frequency" in response.message.lower()

    response = agent.handle_user_message("Every 1 hour")

    assert response.requires_action == "confirm_preferences"
    assert response.profile.digest_schedule == "Every 1 hour"
    assert response.profile.schedule_provided is True


def test_agent_persists_approved_sent_and_unresolved_digest_state(tmp_path):
    db_path = tmp_path / "agent.db"
    db = FanPulseDB(str(db_path))
    agent = FanPulseAgent(db)

    response = agent.handle_user_message(
        "I am Mansoor. I follow the Lakers. Send my digest every Friday morning "
        "to +14155550123 on WhatsApp. Use Pacific time."
    )
    assert response.requires_action == "confirm_preferences"
    response = agent.confirm_preferences()
    assert response.requires_action == "approve_digest"
    response = agent.approve_and_send_digest()
    assert response.requires_action == "complete"

    with sqlite3.connect(db_path) as connection:
        payload_json = connection.execute(
            "select payload_json from digest_history order by id desc limit 1"
        ).fetchone()[0]

    payload = json.loads(payload_json)
    assert payload["approved"] is True
    assert payload["sent"] is True
    assert payload["unresolved"] == []


def test_agent_retries_failed_primary_team_event_fetch_once(tmp_path, monkeypatch):
    import fanpulse_agent.agent as agent_module
    import fanpulse_agent.tools as tools_module

    db_path = tmp_path / "agent.db"
    db = FanPulseDB(str(db_path))
    agent = FanPulseAgent(db)
    calls = []

    def fail_once_then_succeed(team_id):
        calls.append(team_id)
        if len(calls) == 1:
            return ToolResult(
                "thesportsdb.get_next_team_events",
                False,
                {"team_id": team_id, "events": []},
                "https://www.thesportsdb.com/",
                "temporary outage",
                0.2,
                True,
            )
        return tools_module.get_next_team_events_thesportsdb(team_id)

    monkeypatch.setattr(
        agent_module, "get_next_team_events_thesportsdb", fail_once_then_succeed
    )

    response = agent.handle_user_message(
        "I am Mansoor. I follow the Lakers. Send my digest every Friday morning "
        "to +14155550123 on WhatsApp. Use Pacific time."
    )
    assert response.requires_action == "confirm_preferences"
    response = agent.confirm_preferences()

    assert response.requires_action == "approve_digest"
    assert len(calls) == 2
    assert response.digest is not None
    assert [event.entity_name for event in response.digest.events] == ["Los Angeles Lakers"]
    assert response.digest.unresolved == []
    with sqlite3.connect(db_path) as connection:
        fetch_runs = connection.execute(
            """
            select success
            from tool_runs
            where tool_name = 'thesportsdb.get_next_team_events'
            order by id
            """
        ).fetchall()

    assert fetch_runs == [(0,), (1,)]


def test_agent_falls_back_to_web_without_fabricating_event(tmp_path, monkeypatch):
    import fanpulse_agent.agent as agent_module

    db_path = tmp_path / "agent.db"
    db = FanPulseDB(str(db_path))
    agent = FanPulseAgent(db)

    def fail_primary(team_id):
        return ToolResult(
            "thesportsdb.get_next_team_events",
            False,
            {"team_id": team_id, "events": []},
            "https://www.thesportsdb.com/",
            "provider outage",
            0.2,
            True,
        )

    def fail_web(entity_name):
        return ToolResult(
            "web.search_event_source",
            False,
            {"query": entity_name, "events": []},
            "https://search.example.com/fanpulse-mock",
            "no web result",
            0.2,
            True,
        )

    monkeypatch.setattr(agent_module, "get_next_team_events_thesportsdb", fail_primary)
    monkeypatch.setattr(agent_module, "web_search_event_source", fail_web)

    response = agent.handle_user_message(
        "I am Mansoor. I follow the Lakers. Send my digest every Friday morning "
        "to +14155550123 on WhatsApp. Use Pacific time."
    )
    assert response.requires_action == "confirm_preferences"
    response = agent.confirm_preferences()

    assert response.requires_action == "approve_digest"
    assert response.digest is not None
    assert response.digest.events == []
    assert response.digest.unresolved == ["Los Angeles Lakers"]
    with sqlite3.connect(db_path) as connection:
        tool_names = connection.execute(
            "select tool_name from tool_runs order by id"
        ).fetchall()

    assert ("web.search_event_source",) in tool_names


def test_agent_persists_distinct_onboarding_users(tmp_path):
    db_path = tmp_path / "agent.db"
    db = FanPulseDB(str(db_path))

    alice = FanPulseAgent(db)
    response = alice.handle_user_message(
        "I am Alice. I follow the Lakers. Send my digest every Friday morning "
        "to +14155550123 on WhatsApp. Use Pacific time."
    )
    assert response.requires_action == "confirm_preferences"
    response = alice.confirm_preferences()
    assert response.requires_action == "approve_digest"

    bob = FanPulseAgent(db)
    response = bob.handle_user_message(
        "I am Bob. I follow the 49ers. Send my digest every Friday morning "
        "to +14155550124 on WhatsApp. Use Eastern time."
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
        "to +14155550123 on WhatsApp. Use Pacific time."
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


def test_agent_accepts_contact_update_after_digest_approval_block(tmp_path):
    db_path = tmp_path / "agent.db"
    db = FanPulseDB(str(db_path))
    agent = FanPulseAgent(db)
    response = agent.handle_user_message(
        "I am Mansoor. I follow the Lakers and Novak Djokovic. Send my digest every Friday morning. Use Pacific time."
    )
    assert response.requires_action == "confirm_preferences"
    response = agent.confirm_preferences()
    assert response.requires_action == "approve_digest"
    assert response.digest is not None
    original_digest = response.digest

    blocked = agent.approve_and_send_digest()
    assert blocked.requires_action == "collect_contact"
    assert "phone number" in blocked.message

    updated = agent.handle_user_message("Send it to +14155550123 on WhatsApp.")
    assert updated.requires_action == "approve_digest"
    assert updated.digest is original_digest
    assert updated.profile.phone_number == "+14155550123"
    assert updated.profile.whatsapp_consent is True

    sent = agent.approve_and_send_digest()
    assert sent.requires_action == "complete"
    assert sent.digest is original_digest
    assert sent.digest.sent is True


def test_agent_collects_contact_without_reconfirming_preferences(tmp_path):
    db_path = tmp_path / "agent.db"
    db = FanPulseDB(str(db_path))
    agent = FanPulseAgent(db)
    response = agent.handle_user_message(
        "I am Mansoor. I follow the Lakers and Novak Djokovic. Send my digest every Friday morning. Use Pacific time."
    )
    assert response.requires_action == "confirm_preferences"
    response = agent.confirm_preferences()
    assert response.requires_action == "approve_digest"
    original_digest = response.digest

    blocked = agent.approve_and_send_digest()

    assert blocked.requires_action == "collect_contact"
    assert blocked.digest is original_digest
    assert "phone number" in blocked.message


def test_agent_does_not_offer_approval_after_incomplete_contact_update(tmp_path):
    db_path = tmp_path / "agent.db"
    db = FanPulseDB(str(db_path))
    agent = FanPulseAgent(db)
    agent.handle_user_message("I am Mansoor. I follow the Lakers. Use Pacific time.")
    response = agent.confirm_preferences()
    original_digest = response.digest

    blocked = agent.approve_and_send_digest()
    assert blocked.requires_action == "collect_contact"

    update = agent.handle_user_message("Yes, send it on WhatsApp.")

    assert update.requires_action == "collect_contact"
    assert update.digest is original_digest
    assert update.profile.whatsapp_consent is True
    assert update.profile.phone_number is None
    assert "phone number" in update.message


def test_agent_treats_phone_reply_as_whatsapp_contact_in_pending_send_flow(tmp_path):
    db_path = tmp_path / "agent.db"
    db = FanPulseDB(str(db_path))
    agent = FanPulseAgent(db)
    agent.handle_user_message("I am Mansoor. I follow the Lakers. Use Pacific time.")
    response = agent.confirm_preferences()
    original_digest = response.digest

    blocked = agent.approve_and_send_digest()
    assert blocked.requires_action == "collect_contact"

    update = agent.handle_user_message("415-555-0123")

    assert update.requires_action == "approve_digest"
    assert update.digest is original_digest
    assert update.profile.phone_number == "+14155550123"
    assert update.profile.whatsapp_consent is True


def test_weekly_job_runs_for_enrolled_user(tmp_path):
    from weekly_digest_job import run_weekly_digest_job

    db_path = tmp_path / "weekly.db"
    db = FanPulseDB(str(db_path))
    agent = FanPulseAgent(db)
    agent.handle_user_message(
        "I am Mansoor. I follow the Lakers and Real Madrid. Send my digest every Friday morning "
        "to +14155550123 on WhatsApp. Use Pacific time."
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
        "to +14155550123 on WhatsApp. Use Pacific time."
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


def test_weekly_job_run_key_respects_hourly_frequency():
    from datetime import datetime, timezone

    from weekly_digest_job import _current_run_key

    first_hour = datetime(2026, 6, 17, 18, 30, tzinfo=timezone.utc)
    next_hour = datetime(2026, 6, 17, 19, 0, tzinfo=timezone.utc)

    assert _current_run_key("Every 1 hour", first_hour) == "2026-06-17T18"
    assert _current_run_key("Every 1 hour", next_hour) == "2026-06-17T19"
    assert _current_run_key("Friday morning", first_hour) == "2026-W25"


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
