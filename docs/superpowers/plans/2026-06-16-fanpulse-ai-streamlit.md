# FanPulse AI Streamlit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the mock-first FanPulse AI Streamlit sports digest agent with chat onboarding, MCP-ready tool contracts, SQLite state, approval gates, debug trace, and a weekly digest job.

**Architecture:** Keep the Streamlit UI thin and put agent behavior in focused package modules. The agent calls a registry of structured mock tools with stable MCP-style names, logs every decision/tool run to SQLite, and exposes HITL states for ambiguity, preference save, and digest send approval.

**Tech Stack:** Python 3.11+, Streamlit, SQLite, dataclasses, python-dotenv, pytest.

---

## File Structure

- Create `app.py`: Streamlit page, dark prototype-inspired CSS, chat rendering, action buttons, debug expander, manual weekly trigger.
- Create `src/fanpulse_agent/models.py`: dataclasses and serialization helpers.
- Create `src/fanpulse_agent/database.py`: SQLite connection, schema initialization, save/load helpers.
- Create `src/fanpulse_agent/entity_extraction.py`: deterministic extraction and normalization.
- Create `src/fanpulse_agent/tools.py`: required mock-first tool functions and tool registry.
- Create `src/fanpulse_agent/agent.py`: planner, chat state transitions, digest flow, retry/fallback orchestration.
- Create `weekly_digest_job.py`: scheduled-job compatible runner.
- Create `.env.example`: provider key placeholders and database path.
- Create `tests/test_entity_extraction.py`: extraction coverage.
- Create `tests/test_agent_flow.py`: planner, digest, approval, persistence coverage.
- Modify `requirements.txt`: add `streamlit` and `pytest`.
- Modify `README.md`: run commands and demo flow.

---

### Task 1: Dependencies And Environment Template

**Files:**
- Modify: `requirements.txt`
- Create: `.env.example`

- [ ] **Step 1: Update runtime and test dependencies**

Edit `requirements.txt` to contain:

```text
requests>=2.31.0
python-dotenv>=1.0.0
openai>=1.0.0
streamlit>=1.35.0
pytest>=8.0.0
```

- [ ] **Step 2: Add environment template**

Create `.env.example`:

```text
THESPORTSDB_API_KEY=
APIFOOTBALL_API_KEY=
SERPAPI_API_KEY=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_FROM=
FANPULSE_DB_PATH=fanpulse.db
```

- [ ] **Step 3: Verify dependency file is readable**

Run: `python3 -m compileall src`

Expected: exits with status 0 and lists compiled package files.

- [ ] **Step 4: Commit**

Run:

```bash
git add requirements.txt .env.example
git commit -m "chore: add app dependencies and env template"
```

---

### Task 2: Domain Models

**Files:**
- Create: `src/fanpulse_agent/models.py`
- Test: `tests/test_entity_extraction.py`

- [ ] **Step 1: Write model import smoke test**

Create `tests/test_entity_extraction.py` with:

```python
from fanpulse_agent.models import SportsEntity, ToolResult


def test_models_serialize_to_dict():
    entity = SportsEntity(name="Los Angeles Lakers", entity_type="team", sport="basketball")
    result = ToolResult(
        tool_name="sportsdb.search_team",
        success=True,
        data={"name": entity.name},
        source_url="https://www.thesportsdb.com/",
        error=None,
        confidence=0.95,
        mock=True,
    )

    assert entity.to_dict()["sport"] == "basketball"
    assert result.to_dict()["tool_name"] == "sportsdb.search_team"
    assert result.to_dict()["mock"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_entity_extraction.py::test_models_serialize_to_dict -v`

Expected: FAIL because `fanpulse_agent.models` does not exist.

- [ ] **Step 3: Implement models**

Create `src/fanpulse_agent/models.py`:

```python
"""Core dataclasses for FanPulse AI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SportsEntity:
    name: str
    entity_type: str
    sport: str
    source_text: str = ""
    confidence: float = 0.9
    needs_clarification: bool = False
    clarification_prompt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UserProfile:
    name: str = "Fan"
    phone_number: str | None = None
    timezone: str = "America/Los_Angeles"
    digest_schedule: str = "Friday morning"
    whatsapp_consent: bool = False
    teams: list[SportsEntity] = field(default_factory=list)
    athletes: list[SportsEntity] = field(default_factory=list)
    sports: list[str] = field(default_factory=list)
    clarification_choices: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["teams"] = [team.to_dict() for team in self.teams]
        payload["athletes"] = [athlete.to_dict() for athlete in self.athletes]
        return payload


@dataclass
class Event:
    sport_icon: str
    entity_name: str
    event_name: str
    opponent: str | None
    starts_at: str
    display_time: str
    league: str
    source_url: str
    confidence: float
    mock: bool = True
    incomplete: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Digest:
    title: str
    text: str
    events: list[Event] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    approved: bool = False
    sent: bool = False
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["events"] = [event.to_dict() for event in self.events]
        return payload


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    data: dict[str, Any]
    source_url: str | None
    error: str | None
    confidence: float
    mock: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TraceEntry:
    stage: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_entity_extraction.py::test_models_serialize_to_dict -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/fanpulse_agent/models.py tests/test_entity_extraction.py
git commit -m "feat: add FanPulse domain models"
```

---

### Task 3: Entity Extraction

**Files:**
- Create: `src/fanpulse_agent/entity_extraction.py`
- Modify: `tests/test_entity_extraction.py`

- [ ] **Step 1: Add extraction tests**

Append to `tests/test_entity_extraction.py`:

```python
from fanpulse_agent.entity_extraction import extract_profile_from_text


def test_extracts_sample_onboarding_entities():
    text = (
        "I am Mansoor. I follow the Lakers, Real Madrid, India cricket, "
        "Novak Djokovic and Max Verstappen. Send my digest every Friday morning "
        "to +14155550123 on WhatsApp."
    )

    profile, ambiguous = extract_profile_from_text(text)

    assert profile.name == "Mansoor"
    assert profile.phone_number == "+14155550123"
    assert profile.digest_schedule == "Friday morning"
    assert profile.whatsapp_consent is True
    assert [team.name for team in profile.teams] == [
        "Los Angeles Lakers",
        "Real Madrid",
        "India Cricket",
    ]
    assert [athlete.name for athlete in profile.athletes] == [
        "Novak Djokovic",
        "Max Verstappen",
    ]
    assert set(profile.sports) >= {"basketball", "soccer", "cricket", "tennis", "formula 1"}
    assert ambiguous[0].name == "India Cricket"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_entity_extraction.py -v`

Expected: FAIL because `entity_extraction.py` does not exist.

- [ ] **Step 3: Implement deterministic extractor**

Create `src/fanpulse_agent/entity_extraction.py`:

```python
"""Deterministic mock extraction for chat onboarding."""

from __future__ import annotations

import re

from fanpulse_agent.models import SportsEntity, UserProfile


KNOWN_ENTITIES = {
    "lakers": SportsEntity("Los Angeles Lakers", "team", "basketball", confidence=0.96),
    "los angeles lakers": SportsEntity("Los Angeles Lakers", "team", "basketball", confidence=0.98),
    "real madrid": SportsEntity("Real Madrid", "team", "soccer", confidence=0.98),
    "49ers": SportsEntity("San Francisco 49ers", "team", "american football", confidence=0.94),
    "san francisco 49ers": SportsEntity("San Francisco 49ers", "team", "american football", confidence=0.98),
    "india cricket": SportsEntity(
        "India Cricket",
        "team",
        "cricket",
        confidence=0.72,
        needs_clarification=True,
        clarification_prompt="Did you mean India men's national cricket team, women's team, or both?",
    ),
    "novak djokovic": SportsEntity("Novak Djokovic", "athlete", "tennis", confidence=0.97),
    "djokovic": SportsEntity("Novak Djokovic", "athlete", "tennis", confidence=0.93),
    "max verstappen": SportsEntity("Max Verstappen", "athlete", "formula 1", confidence=0.97),
    "verstappen": SportsEntity("Max Verstappen", "athlete", "formula 1", confidence=0.92),
}


def extract_profile_from_text(text: str) -> tuple[UserProfile, list[SportsEntity]]:
    lowered = text.lower()
    profile = UserProfile()
    ambiguous: list[SportsEntity] = []

    name_match = re.search(r"\b(?:i am|i'm|my name is)\s+([A-Z][A-Za-z'-]+)", text)
    if name_match:
        profile.name = name_match.group(1)

    phone_match = re.search(r"(\+\d[\d\s().-]{7,}\d)", text)
    if phone_match:
        profile.phone_number = re.sub(r"[\s().-]", "", phone_match.group(1))

    if "whatsapp" in lowered or "send" in lowered:
        profile.whatsapp_consent = True

    if "friday morning" in lowered:
        profile.digest_schedule = "Friday morning"
    elif "monday morning" in lowered:
        profile.digest_schedule = "Monday morning"
    elif "weekly" in lowered:
        profile.digest_schedule = "Weekly"

    if "pt" in lowered or "pacific" in lowered:
        profile.timezone = "America/Los_Angeles"
    elif "et" in lowered or "eastern" in lowered:
        profile.timezone = "America/New_York"
    elif "india" in lowered or "ist" in lowered:
        profile.timezone = "Asia/Kolkata"

    seen: set[str] = set()
    for alias, entity in KNOWN_ENTITIES.items():
        if alias in lowered and entity.name not in seen:
            copied = SportsEntity(**entity.to_dict())
            copied.source_text = alias
            seen.add(copied.name)
            if copied.entity_type == "team":
                profile.teams.append(copied)
            else:
                profile.athletes.append(copied)
            if copied.sport not in profile.sports:
                profile.sports.append(copied.sport)
            if copied.needs_clarification:
                ambiguous.append(copied)

    return profile, ambiguous
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/test_entity_extraction.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/fanpulse_agent/entity_extraction.py tests/test_entity_extraction.py
git commit -m "feat: add mock sports entity extraction"
```

---

### Task 4: SQLite Persistence

**Files:**
- Create: `src/fanpulse_agent/database.py`
- Modify: `tests/test_agent_flow.py`

- [ ] **Step 1: Write database initialization test**

Create `tests/test_agent_flow.py`:

```python
import sqlite3

from fanpulse_agent.database import FanPulseDB
from fanpulse_agent.models import ToolResult, TraceEntry, UserProfile


def test_database_creates_tables_and_logs_records(tmp_path):
    db_path = tmp_path / "fanpulse-test.db"
    db = FanPulseDB(str(db_path))
    db.initialize()

    user_id = db.save_user_preferences(UserProfile(name="Mansoor", phone_number="+14155550123"))
    db.log_tool_run(user_id, ToolResult("sqlite.save_state", True, {"user_id": user_id}, None, None, 1.0))
    db.log_trace(user_id, TraceEntry("test", "trace saved", {"ok": True}))

    with sqlite3.connect(db_path) as conn:
        users = conn.execute("select count(*) from users").fetchone()[0]
        tool_runs = conn.execute("select count(*) from tool_runs").fetchone()[0]
        traces = conn.execute("select count(*) from agent_trace").fetchone()[0]

    assert users == 1
    assert tool_runs == 1
    assert traces == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_agent_flow.py::test_database_creates_tables_and_logs_records -v`

Expected: FAIL because `database.py` does not exist.

- [ ] **Step 3: Implement SQLite helper**

Create `src/fanpulse_agent/database.py` with schema creation for `users`, `preferences`, `sports_entities`, `digest_history`, `tool_runs`, and `agent_trace`; implement `initialize`, `save_user_preferences`, `log_tool_run`, `log_trace`, `save_digest_history`, and `load_enrolled_users`.

The implementation should JSON-serialize profile, entities, digests, tool payloads, and trace payloads with `json.dumps`.

- [ ] **Step 4: Run database test**

Run: `PYTHONPATH=src pytest tests/test_agent_flow.py::test_database_creates_tables_and_logs_records -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/fanpulse_agent/database.py tests/test_agent_flow.py
git commit -m "feat: add SQLite persistence"
```

---

### Task 5: Mock Tool Registry

**Files:**
- Create: `src/fanpulse_agent/tools.py`
- Modify: `tests/test_agent_flow.py`

- [ ] **Step 1: Add tool tests**

Append to `tests/test_agent_flow.py`:

```python
from fanpulse_agent.models import UserProfile
from fanpulse_agent.tools import (
    generate_digest,
    get_next_team_events_thesportsdb,
    normalize_sports_entity,
    rank_events,
    search_team_thesportsdb,
    web_search_event_source,
)


def test_mock_tools_return_structured_results():
    normalized = normalize_sports_entity("Lakers")
    team = search_team_thesportsdb("Los Angeles Lakers")
    events = get_next_team_events_thesportsdb(team.data["team_id"])
    athlete = web_search_event_source("Novak Djokovic")
    ranked = rank_events(events.data["events"] + athlete.data["events"], UserProfile(name="Mansoor"))
    digest = generate_digest(ranked.data["events"], UserProfile(name="Mansoor"))

    assert normalized.success is True
    assert team.data["team_id"] == "lakers"
    assert events.data["events"][0].entity_name == "Los Angeles Lakers"
    assert athlete.data["events"][0].entity_name == "Novak Djokovic"
    assert "FanPulse Weekly Digest" in digest.data["digest"].title
    assert all(result.mock for result in [normalized, team, events, athlete, ranked, digest])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_agent_flow.py::test_mock_tools_return_structured_results -v`

Expected: FAIL because `tools.py` does not exist.

- [ ] **Step 3: Implement mock tools**

Create `src/fanpulse_agent/tools.py` with the required functions from the spec. Use deterministic event data for Lakers, Real Madrid, San Francisco 49ers, India Cricket, Novak Djokovic, and Max Verstappen. Return `ToolResult` from every function. Use `Event` and `Digest` dataclasses for generated event and digest data.

The WhatsApp sender must not send a real message. It returns a successful `ToolResult` with `mock=True`, the phone number, and digest character count.

- [ ] **Step 4: Run tool tests**

Run: `PYTHONPATH=src pytest tests/test_agent_flow.py::test_mock_tools_return_structured_results -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/fanpulse_agent/tools.py tests/test_agent_flow.py
git commit -m "feat: add mock MCP-ready tools"
```

---

### Task 6: Agent Planner And HITL Flow

**Files:**
- Create: `src/fanpulse_agent/agent.py`
- Modify: `tests/test_agent_flow.py`

- [ ] **Step 1: Add agent flow tests**

Append to `tests/test_agent_flow.py`:

```python
from fanpulse_agent.agent import FanPulseAgent


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_agent_flow.py::test_agent_runs_sample_flow_with_approval_gates -v`

Expected: FAIL because `agent.py` does not exist.

- [ ] **Step 3: Implement agent**

Create `src/fanpulse_agent/agent.py` with:

- `AgentResponse` dataclass containing `message`, `requires_action`, `profile`, `digest`, and `trace`.
- `FanPulseAgent.__init__(db)`.
- `handle_user_message(text)` to extract profile, log plan, ask clarification if needed.
- `resolve_ambiguity(choice)` to store the clarification choice.
- `confirm_preferences()` to save profile, run event tools, rank events, generate digest, and ask for approval.
- `approve_and_send_digest()` to call mock WhatsApp only when consent and phone number exist, save digest history, and return completion.
- `run_weekly_digest_for_profile(profile)` for scheduled execution.

The planner must log selected tool names and every tool result to SQLite.

- [ ] **Step 4: Run agent tests**

Run: `PYTHONPATH=src pytest tests/test_agent_flow.py::test_agent_runs_sample_flow_with_approval_gates -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/fanpulse_agent/agent.py tests/test_agent_flow.py
git commit -m "feat: add FanPulse agent flow"
```

---

### Task 7: Streamlit App

**Files:**
- Create: `app.py`
- Modify: `README.md`

- [ ] **Step 1: Implement Streamlit UI**

Create `app.py` with:

- `st.set_page_config(page_title="FanPulse AI", page_icon="🏆", layout="wide")`.
- Dark CSS matching the prototype direction.
- Session state for `messages`, `agent`, `last_response`, and `db`.
- Left column with FanPulse identity, status, sample button, weekly-run button, and profile summary.
- Right column with chat messages via `st.chat_message()`, `st.chat_input()`, ambiguity buttons, preference confirmation button, digest approval button, and digest preview cards.
- Debug expander that renders trace entries and selected tool runs.

- [ ] **Step 2: Update README**

Update `README.md` to explain:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Include sample onboarding text and note that missing keys run mock mode.

- [ ] **Step 3: Verify app imports**

Run: `PYTHONPATH=src python3 -m compileall app.py src weekly_digest_job.py`

Expected: exits with status 0 after `weekly_digest_job.py` exists in Task 8. If Task 8 has not run yet, use `PYTHONPATH=src python3 -m compileall app.py src`.

- [ ] **Step 4: Commit**

Run:

```bash
git add app.py README.md
git commit -m "feat: add Streamlit chat app"
```

---

### Task 8: Weekly Digest Job

**Files:**
- Create: `weekly_digest_job.py`
- Modify: `src/fanpulse_agent/main.py`
- Modify: `tests/test_agent_flow.py`

- [ ] **Step 1: Add weekly job test**

Append to `tests/test_agent_flow.py`:

```python
from weekly_digest_job import run_weekly_digest_job


def test_weekly_job_runs_for_enrolled_user(tmp_path):
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_agent_flow.py::test_weekly_job_runs_for_enrolled_user -v`

Expected: FAIL because `weekly_digest_job.py` does not exist.

- [ ] **Step 3: Implement weekly job**

Create `weekly_digest_job.py` with `run_weekly_digest_job(db_path: str | None = None) -> dict[str, int]`. It initializes the DB, loads enrolled users, calls `FanPulseAgent.run_weekly_digest_for_profile`, saves history, and returns counts.

Update `src/fanpulse_agent/main.py` so running `python -m fanpulse_agent.main` invokes the weekly digest job and prints the summary.

- [ ] **Step 4: Run weekly job test**

Run: `PYTHONPATH=src pytest tests/test_agent_flow.py::test_weekly_job_runs_for_enrolled_user -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add weekly_digest_job.py src/fanpulse_agent/main.py tests/test_agent_flow.py
git commit -m "feat: add weekly digest job"
```

---

### Task 9: Full Verification And Local Demo

**Files:**
- No new files unless verification exposes a focused bug.

- [ ] **Step 1: Run full tests**

Run: `PYTHONPATH=src pytest -v`

Expected: all tests PASS.

- [ ] **Step 2: Run compile check**

Run: `PYTHONPATH=src python3 -m compileall app.py weekly_digest_job.py src`

Expected: exits with status 0.

- [ ] **Step 3: Start Streamlit**

Run: `.venv/bin/streamlit run app.py`

Expected: local Streamlit server starts and prints a localhost URL. If `.venv` does not exist or Streamlit is not installed, install dependencies first with `.venv/bin/pip install -r requirements.txt`.

- [ ] **Step 4: Exercise sample flow**

In the browser:

1. Click the sample onboarding button.
2. Confirm India Cricket ambiguity.
3. Confirm preferences.
4. Preview digest.
5. Approve and send.
6. Open Agent Trace / Debug View.

Expected: digest sends in mock mode, trace includes planner steps and mock tool calls, and database contains users, tool runs, traces, and digest history.

- [ ] **Step 5: Final status**

Run: `git status --short`

Expected: clean worktree except for generated local files such as `fanpulse.db`, `__pycache__`, or test cache. Generated files should be ignored or removed before final handoff.

