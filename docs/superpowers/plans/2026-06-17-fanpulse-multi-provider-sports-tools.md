# FanPulse Multi-Provider Sports Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add MCP-style local tools for API-SPORTS Basketball, API-SPORTS Formula 1, and SerpAPI so the LLM planner can route sports lookups to the right provider.

**Architecture:** Provider clients perform HTTP calls and preserve provider errors. Tool wrappers normalize payloads into the existing `Event` and `ToolResult` models. The agent keeps its chat/UI flow unchanged and selects provider tools through deterministic routing plus the OpenAI planner metadata.

**Tech Stack:** Python 3.9, Streamlit, pytest, requests, existing FanPulse dataclasses, existing OpenAI planner.

---

## File Structure

- Create `src/fanpulse_agent/apisports_basketball_client.py`: Basketball API-SPORTS client for team, league, and game payloads.
- Create `src/fanpulse_agent/apisports_formula1_client.py`: Formula 1 API-SPORTS client for driver and race payloads.
- Create `src/fanpulse_agent/serpapi_client.py`: SerpAPI client for event/news fallback search.
- Modify `src/fanpulse_agent/tools.py`: Add tool wrappers, live enable flags, event normalizers, registry entries, and fallback mocks.
- Modify `src/fanpulse_agent/agent.py`: Route basketball and Formula 1 entities through the new tools before existing fallbacks.
- Modify `src/fanpulse_agent/agent_planner.py`: Expose new tool names to the LLM planner and deterministic fallback.
- Modify `.env.example`: Add provider keys and live-disable flags.
- Create `tests/test_multi_provider_tools.py`: Deterministic fake-client tests for Basketball, Formula 1, SerpAPI, and agent routing.

---

### Task 1: Add Basketball Provider Client And Tool Wrappers

**Files:**
- Create: `src/fanpulse_agent/apisports_basketball_client.py`
- Modify: `src/fanpulse_agent/tools.py`
- Test: `tests/test_multi_provider_tools.py`

- [ ] **Step 1: Write failing Basketball tests**

Add these tests to `tests/test_multi_provider_tools.py`:

```python
from fanpulse_agent.tools import (
    get_team_games_apibasketball,
    search_team_apibasketball,
)


def _basketball_game_payload():
    return {
        "id": 7001,
        "date": "2999-10-21T02:00:00+00:00",
        "league": {"id": 12, "name": "NBA"},
        "teams": {
            "home": {"id": 99, "name": "Los Angeles Lakers"},
            "away": {"id": 100, "name": "Golden State Warriors"},
        },
    }


def test_live_basketball_team_games_use_api_sports_client(monkeypatch):
    class FakeClient:
        last_errors = None

        def search_team(self, name):
            assert name == "Los Angeles Lakers"
            return {"id": 99, "name": "Los Angeles Lakers"}

        def next_team_games(self, team_id):
            assert team_id == 99
            return [_basketball_game_payload()]

    monkeypatch.setenv("APISPORTS_BASKETBALL_API_KEY", "test-key")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_APISPORTS_BASKETBALL", raising=False)
    monkeypatch.setattr("fanpulse_agent.tools.APISportsBasketballClient", lambda: FakeClient())

    team = search_team_apibasketball("Los Angeles Lakers")
    games = get_team_games_apibasketball(99, "Los Angeles Lakers")

    assert team.success is True
    assert team.mock is False
    assert team.data["team_id"] == 99
    assert games.success is True
    assert games.mock is False
    event = games.data["events"][0]
    assert event.title == "Los Angeles Lakers vs Golden State Warriors"
    assert event.entity_name == "Los Angeles Lakers"
    assert event.metadata["provider"] == "api-basketball"
    assert event.metadata["game_id"] == 7001
```

- [ ] **Step 2: Run Basketball test to verify it fails**

Run:

```bash
FANPULSE_DISABLE_LLM=1 FANPULSE_DISABLE_LIVE_SPORTSDB=1 FANPULSE_DISABLE_LIVE_APIFOOTBALL=1 FANPULSE_DISABLE_LIVE_APISPORTS_BASKETBALL=1 FANPULSE_DISABLE_LIVE_APISPORTS_FORMULA1=1 FANPULSE_DISABLE_LIVE_SERPAPI=1 PYTHONPATH=src PYTHONPYCACHEPREFIX=.pytest_cache/pycache .venv/bin/python -m pytest tests/test_multi_provider_tools.py::test_live_basketball_team_games_use_api_sports_client
```

Expected: FAIL because `search_team_apibasketball` and `get_team_games_apibasketball` are not defined.

- [ ] **Step 3: Implement Basketball client**

Create `src/fanpulse_agent/apisports_basketball_client.py`:

```python
from __future__ import annotations

import os
from typing import Any, Optional

import requests

APISPORTS_BASKETBALL_BASE_URL = "https://v1.basketball.api-sports.io"

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


class APISportsBasketballClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = APISPORTS_BASKETBALL_BASE_URL,
        timeout: float = 8.0,
    ):
        self.api_key = (
            api_key
            or os.environ.get("APISPORTS_BASKETBALL_API_KEY")
            or os.environ.get("APIFOOTBALL_API_KEY")
            or ""
        )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.last_errors: Any = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def search_team(self, name: str) -> Optional[dict[str, Any]]:
        payload = self._get("teams", {"search": name})
        return self._first(payload.get("response"))

    def next_team_games(self, team_id: int) -> list[dict[str, Any]]:
        payload = self._get("games", {"team": str(team_id), "next": "5"})
        return self._list(payload.get("response"))

    def search_league(self, name: str) -> Optional[dict[str, Any]]:
        payload = self._get("leagues", {"search": name})
        return self._first(payload.get("response"))

    def next_league_games(self, league_id: int) -> list[dict[str, Any]]:
        payload = self._get("games", {"league": str(league_id), "next": "5"})
        return self._list(payload.get("response"))

    def _get(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if not self.enabled:
            self.last_errors = {"auth": "APISPORTS_BASKETBALL_API_KEY is not configured."}
            return {}
        response = requests.get(
            f"{self.base_url}/{endpoint}",
            headers={"x-apisports-key": self.api_key},
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            self.last_errors = {"payload": "Provider returned a non-object response."}
            return {}
        self.last_errors = payload.get("errors")
        return payload

    def _first(self, value: Any) -> Optional[dict[str, Any]]:
        values = self._list(value)
        return values[0] if values else None

    def _list(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]
```

- [ ] **Step 4: Implement Basketball tools**

Modify `src/fanpulse_agent/tools.py`:

```python
from fanpulse_agent.apisports_basketball_client import APISportsBasketballClient
```

Add:

```python
API_BASKETBALL_SOURCE_URL = "https://api-sports.io/basketball"


def _apibasketball_live_enabled() -> bool:
    return bool(
        (os.environ.get("APISPORTS_BASKETBALL_API_KEY") or os.environ.get("APIFOOTBALL_API_KEY"))
        and os.environ.get("FANPULSE_DISABLE_LIVE_APISPORTS_BASKETBALL") != "1"
    )


def search_team_apibasketball(entity_name: str) -> ToolResult:
    if _apibasketball_live_enabled():
        return _search_team_apibasketball_live(entity_name)
    return _result(
        "api-basketball.search_team",
        False,
        {"query": entity_name},
        API_BASKETBALL_SOURCE_URL,
        error=f"No API-Basketball mock team found for {entity_name}",
        confidence=0.2,
    )


def get_team_games_apibasketball(team_id: int, team_name: Optional[str] = None) -> ToolResult:
    if _apibasketball_live_enabled():
        return _get_team_games_apibasketball_live(team_id, team_name)
    events = [_make_event(payload) for payload in MOCK_EVENTS.get("lakers", [])]
    return _result(
        "api-basketball.get_team_games",
        bool(events),
        {"team_id": team_id, "events": events},
        API_BASKETBALL_SOURCE_URL,
        error=None if events else f"No API-Basketball mock games found for team_id {team_id}",
        confidence=0.88 if events else 0.25,
    )
```

Add private live helpers and `_make_apibasketball_event()` matching the tested fields. Add registry entries:

```python
"api-basketball.search_team": search_team_apibasketball,
"api-basketball.get_team_games": get_team_games_apibasketball,
```

- [ ] **Step 5: Run Basketball test to verify it passes**

Run the same focused pytest command from Step 2.

Expected: PASS.

---

### Task 2: Add Formula 1 Provider Client And Tool Wrappers

**Files:**
- Create: `src/fanpulse_agent/apisports_formula1_client.py`
- Modify: `src/fanpulse_agent/tools.py`
- Test: `tests/test_multi_provider_tools.py`

- [ ] **Step 1: Write failing Formula 1 tests**

Add:

```python
from fanpulse_agent.tools import (
    get_next_races_apiformula1,
    search_driver_apiformula1,
)


def _formula1_race_payload():
    return {
        "id": 501,
        "competition": {"name": "Formula 1"},
        "circuit": {"name": "Silverstone Circuit"},
        "race": {"date": "2999-07-07", "time": "14:00:00+00:00"},
        "season": 2999,
        "type": "Race",
    }


def test_live_formula1_driver_races_use_api_sports_client(monkeypatch):
    class FakeClient:
        last_errors = None

        def search_driver(self, name):
            assert name == "Max Verstappen"
            return {"id": 25, "name": "Max Verstappen"}

        def next_races(self):
            return [_formula1_race_payload()]

    monkeypatch.setenv("APISPORTS_FORMULA1_API_KEY", "test-key")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_APISPORTS_FORMULA1", raising=False)
    monkeypatch.setattr("fanpulse_agent.tools.APISportsFormula1Client", lambda: FakeClient())

    driver = search_driver_apiformula1("Max Verstappen")
    races = get_next_races_apiformula1("Max Verstappen")

    assert driver.success is True
    assert driver.mock is False
    assert driver.data["driver_id"] == 25
    assert races.success is True
    event = races.data["events"][0]
    assert event.title == "Formula 1 at Silverstone Circuit"
    assert event.entity_name == "Max Verstappen"
    assert event.metadata["provider"] == "api-formula1"
    assert event.metadata["race_id"] == 501
```

- [ ] **Step 2: Run Formula 1 test to verify it fails**

Run:

```bash
FANPULSE_DISABLE_LLM=1 FANPULSE_DISABLE_LIVE_SPORTSDB=1 FANPULSE_DISABLE_LIVE_APIFOOTBALL=1 FANPULSE_DISABLE_LIVE_APISPORTS_BASKETBALL=1 FANPULSE_DISABLE_LIVE_APISPORTS_FORMULA1=1 FANPULSE_DISABLE_LIVE_SERPAPI=1 PYTHONPATH=src PYTHONPYCACHEPREFIX=.pytest_cache/pycache .venv/bin/python -m pytest tests/test_multi_provider_tools.py::test_live_formula1_driver_races_use_api_sports_client
```

Expected: FAIL because Formula 1 tool functions are not defined.

- [ ] **Step 3: Implement Formula 1 client and tools**

Create `src/fanpulse_agent/apisports_formula1_client.py` with the same shape as the Basketball client, using base URL `https://v1.formula-1.api-sports.io`, endpoints `drivers` with `search`, and `races` with `next=5`.

Modify `src/fanpulse_agent/tools.py` to add:

```python
API_FORMULA1_SOURCE_URL = "https://api-sports.io/formula-1"
```

Add public tools:

```python
def search_driver_apiformula1(entity_name: str) -> ToolResult: ...
def get_next_races_apiformula1(entity_name: Optional[str] = None) -> ToolResult: ...
def get_driver_context_apiformula1(driver_id: int, driver_name: Optional[str] = None) -> ToolResult: ...
```

Normalize races in `_make_apiformula1_event()` with provider `api-formula1`, sport `formula 1`, event type `race`, and race IDs in metadata. Add registry entries for the three `api-formula1.*` tools.

- [ ] **Step 4: Run Formula 1 test to verify it passes**

Run the focused pytest command from Step 2.

Expected: PASS.

---

### Task 3: Add SerpAPI Fallback Client And Tools

**Files:**
- Create: `src/fanpulse_agent/serpapi_client.py`
- Modify: `src/fanpulse_agent/tools.py`
- Test: `tests/test_multi_provider_tools.py`

- [ ] **Step 1: Write failing SerpAPI tests**

Add:

```python
from fanpulse_agent.tools import search_sports_events_serpapi


def test_live_serpapi_event_search_normalizes_results(monkeypatch):
    class FakeClient:
        last_errors = None

        def search(self, query):
            assert "Novak Djokovic" in query
            return [
                {
                    "title": "Novak Djokovic schedule and results",
                    "link": "https://example.com/djokovic",
                    "snippet": "Upcoming tennis schedule for Novak Djokovic.",
                    "date": "2999-06-30",
                }
            ]

    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_SERPAPI", raising=False)
    monkeypatch.setattr("fanpulse_agent.tools.SerpAPIClient", lambda: FakeClient())

    result = search_sports_events_serpapi("Novak Djokovic", "tennis")

    assert result.success is True
    assert result.mock is False
    event = result.data["events"][0]
    assert event.title == "Novak Djokovic schedule and results"
    assert event.source_url == "https://example.com/djokovic"
    assert event.metadata["provider"] == "serpapi"
```

- [ ] **Step 2: Run SerpAPI test to verify it fails**

Run:

```bash
FANPULSE_DISABLE_LLM=1 FANPULSE_DISABLE_LIVE_SPORTSDB=1 FANPULSE_DISABLE_LIVE_APIFOOTBALL=1 FANPULSE_DISABLE_LIVE_APISPORTS_BASKETBALL=1 FANPULSE_DISABLE_LIVE_APISPORTS_FORMULA1=1 FANPULSE_DISABLE_LIVE_SERPAPI=1 PYTHONPATH=src PYTHONPYCACHEPREFIX=.pytest_cache/pycache .venv/bin/python -m pytest tests/test_multi_provider_tools.py::test_live_serpapi_event_search_normalizes_results
```

Expected: FAIL because SerpAPI tool function is not defined.

- [ ] **Step 3: Implement SerpAPI client and tools**

Create `src/fanpulse_agent/serpapi_client.py`:

```python
from __future__ import annotations

import os
from typing import Any

import requests

SERPAPI_BASE_URL = "https://serpapi.com/search.json"

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


class SerpAPIClient:
    def __init__(self, api_key: str | None = None, base_url: str = SERPAPI_BASE_URL, timeout: float = 8.0):
        self.api_key = api_key or os.environ.get("SERPAPI_API_KEY") or ""
        self.base_url = base_url
        self.timeout = timeout
        self.last_errors: Any = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str) -> list[dict[str, Any]]:
        if not self.enabled:
            self.last_errors = {"auth": "SERPAPI_API_KEY is not configured."}
            return []
        response = requests.get(
            self.base_url,
            params={"engine": "google", "q": query, "api_key": self.api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            self.last_errors = {"payload": "Provider returned a non-object response."}
            return []
        self.last_errors = payload.get("error")
        organic = payload.get("organic_results")
        return [item for item in organic if isinstance(item, dict)] if isinstance(organic, list) else []
```

Modify `tools.py` with `search_sports_events_serpapi(entity_name, sport=None)` and `search_sports_news_serpapi(entity_name, sport=None)`. Normalize organic results into low-confidence `Event` values with provider `serpapi`. Add registry entries.

- [ ] **Step 4: Run SerpAPI test to verify it passes**

Run the focused pytest command from Step 2.

Expected: PASS.

---

### Task 4: Route Agent And Planner To New Tools

**Files:**
- Modify: `src/fanpulse_agent/agent.py`
- Modify: `src/fanpulse_agent/agent_planner.py`
- Test: `tests/test_multi_provider_tools.py`

- [ ] **Step 1: Write failing routing tests**

Add:

```python
from fanpulse_agent.agent import FanPulseAgent
from fanpulse_agent.database import FanPulseDB
from fanpulse_agent.models import SportsEntity, UserProfile


def test_agent_uses_basketball_provider_before_sportsdb(tmp_path, monkeypatch):
    import fanpulse_agent.agent as agent_module

    calls = []

    def fake_basketball_events(team_id, team_name=None):
        calls.append(("games", team_id, team_name))
        return get_team_games_apibasketball(team_id, team_name)

    class FakeClient:
        last_errors = None

        def search_team(self, name):
            calls.append(("search", name))
            return {"id": 99, "name": "Los Angeles Lakers"}

        def next_team_games(self, team_id):
            return [_basketball_game_payload()]

    monkeypatch.setenv("APISPORTS_BASKETBALL_API_KEY", "test-key")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_APISPORTS_BASKETBALL", raising=False)
    monkeypatch.setattr("fanpulse_agent.tools.APISportsBasketballClient", lambda: FakeClient())
    monkeypatch.setattr(agent_module, "get_team_games_apibasketball", fake_basketball_events)

    agent = FanPulseAgent(FanPulseDB(str(tmp_path / "agent.db")))
    profile = UserProfile(
        name="Mansoor",
        name_provided=True,
        timezone_provided=True,
        teams=[SportsEntity(name="Los Angeles Lakers", entity_type="team", sport="basketball")],
    )

    events, unresolved = agent._collect_events(profile)

    assert unresolved == []
    assert events[0].metadata["provider"] == "api-basketball"
    assert calls[0] == ("search", "Los Angeles Lakers")


def test_agent_uses_formula1_provider_before_serpapi(tmp_path, monkeypatch):
    import fanpulse_agent.agent as agent_module

    calls = []

    def fake_formula1_races(entity_name=None):
        calls.append(entity_name)
        return get_next_races_apiformula1(entity_name)

    class FakeClient:
        last_errors = None

        def search_driver(self, name):
            return {"id": 25, "name": "Max Verstappen"}

        def next_races(self):
            return [_formula1_race_payload()]

    monkeypatch.setenv("APISPORTS_FORMULA1_API_KEY", "test-key")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_APISPORTS_FORMULA1", raising=False)
    monkeypatch.setattr("fanpulse_agent.tools.APISportsFormula1Client", lambda: FakeClient())
    monkeypatch.setattr(agent_module, "get_next_races_apiformula1", fake_formula1_races)

    agent = FanPulseAgent(FanPulseDB(str(tmp_path / "agent.db")))
    profile = UserProfile(
        name="Mansoor",
        name_provided=True,
        timezone_provided=True,
        athletes=[SportsEntity(name="Max Verstappen", entity_type="athlete", sport="formula 1")],
    )

    events, unresolved = agent._collect_events(profile)

    assert unresolved == []
    assert events[0].metadata["provider"] == "api-formula1"
    assert calls == ["Max Verstappen"]
```

- [ ] **Step 2: Run routing tests to verify they fail**

Run:

```bash
FANPULSE_DISABLE_LLM=1 FANPULSE_DISABLE_LIVE_SPORTSDB=1 FANPULSE_DISABLE_LIVE_APIFOOTBALL=1 FANPULSE_DISABLE_LIVE_APISPORTS_BASKETBALL=1 FANPULSE_DISABLE_LIVE_APISPORTS_FORMULA1=1 FANPULSE_DISABLE_LIVE_SERPAPI=1 PYTHONPATH=src PYTHONPYCACHEPREFIX=.pytest_cache/pycache .venv/bin/python -m pytest tests/test_multi_provider_tools.py::test_agent_uses_basketball_provider_before_sportsdb tests/test_multi_provider_tools.py::test_agent_uses_formula1_provider_before_serpapi
```

Expected: FAIL because the agent does not route these providers yet.

- [ ] **Step 3: Implement agent routing**

Modify `agent.py` imports:

```python
from fanpulse_agent.tools import (
    get_next_races_apiformula1,
    get_team_games_apibasketball,
    search_driver_apiformula1,
    search_sports_events_serpapi,
    search_team_apibasketball,
)
```

In `_collect_team_events()`, route `sport == "basketball"` through `search_team_apibasketball()` and `get_team_games_apibasketball()` before SportsDB.

In the athlete loop, route `athlete.sport == "formula 1"` through `search_driver_apiformula1()` and `get_next_races_apiformula1()` before SerpAPI. Use `search_sports_events_serpapi()` as the fallback before adding unresolved.

- [ ] **Step 4: Implement planner tool names**

Modify `agent_planner.py` fallback plan and LLM prompt to include:

```text
api-basketball.search_team
api-basketball.get_team_games
api-basketball.search_league
api-basketball.get_league_games
api-formula1.search_driver
api-formula1.get_next_races
api-formula1.get_driver_context
serpapi.search_sports_events
serpapi.search_sports_news
```

Prefer Basketball for basketball teams/leagues and Formula 1 for Formula 1 athletes before general fallbacks.

- [ ] **Step 5: Run routing tests to verify they pass**

Run the focused pytest command from Step 2.

Expected: PASS.

---

### Task 5: Environment, Full Verification, And Live Smokes

**Files:**
- Modify: `.env.example`
- Verify: all tests and Streamlit smoke

- [ ] **Step 1: Add environment flags**

Modify `.env.example`:

```dotenv
APISPORTS_BASKETBALL_API_KEY=
FANPULSE_DISABLE_LIVE_APISPORTS_BASKETBALL=0
APISPORTS_FORMULA1_API_KEY=
FANPULSE_DISABLE_LIVE_APISPORTS_FORMULA1=0
FANPULSE_DISABLE_LIVE_SERPAPI=0
```

- [ ] **Step 2: Run full deterministic suite**

Run:

```bash
FANPULSE_DISABLE_LLM=1 FANPULSE_DISABLE_LIVE_SPORTSDB=1 FANPULSE_DISABLE_LIVE_APIFOOTBALL=1 FANPULSE_DISABLE_LIVE_APISPORTS_BASKETBALL=1 FANPULSE_DISABLE_LIVE_APISPORTS_FORMULA1=1 FANPULSE_DISABLE_LIVE_SERPAPI=1 PYTHONPATH=src PYTHONPYCACHEPREFIX=.pytest_cache/pycache .venv/bin/python -m pytest tests
```

Expected: all tests pass.

- [ ] **Step 3: Compile Python files**

Run:

```bash
FANPULSE_DISABLE_LLM=1 FANPULSE_DISABLE_LIVE_SPORTSDB=1 FANPULSE_DISABLE_LIVE_APIFOOTBALL=1 FANPULSE_DISABLE_LIVE_APISPORTS_BASKETBALL=1 FANPULSE_DISABLE_LIVE_APISPORTS_FORMULA1=1 FANPULSE_DISABLE_LIVE_SERPAPI=1 PYTHONPATH=src PYTHONPYCACHEPREFIX=.pytest_cache/pycache .venv/bin/python -m compileall app.py src tests
```

Expected: exit code 0.

- [ ] **Step 4: Run Streamlit import smoke**

Run:

```bash
FANPULSE_DISABLE_LLM=1 FANPULSE_DISABLE_LIVE_SPORTSDB=1 FANPULSE_DISABLE_LIVE_APIFOOTBALL=1 FANPULSE_DISABLE_LIVE_APISPORTS_BASKETBALL=1 FANPULSE_DISABLE_LIVE_APISPORTS_FORMULA1=1 FANPULSE_DISABLE_LIVE_SERPAPI=1 PYTHONPATH=src PYTHONPYCACHEPREFIX=.pytest_cache/pycache .venv/bin/python -c "from streamlit.testing.v1 import AppTest; app = AppTest.from_file('app.py'); app.run(timeout=10); print('exception_count', len(app.exception)); print('main_blocks', len(app.main))"
```

Expected: `exception_count 0`.

- [ ] **Step 5: Run optional live smokes**

Run only after keys are present. Output must never include key values:

```bash
PYTHONPATH=src .venv/bin/python -c "from fanpulse_agent.tools import search_team_apibasketball, get_team_games_apibasketball, search_driver_apiformula1, get_next_races_apiformula1, search_sports_events_serpapi; team=search_team_apibasketball('Los Angeles Lakers'); print('basketball_team_success', team.success, 'mock', team.mock, 'error', team.error); games=get_team_games_apibasketball(team.data.get('team_id', 0), team.data.get('name')) if team.success else None; print('basketball_games_success', getattr(games, 'success', None), 'mock', getattr(games, 'mock', None), 'count', len(games.data.get('events', [])) if games else 0, 'error', getattr(games, 'error', None)); driver=search_driver_apiformula1('Max Verstappen'); print('f1_driver_success', driver.success, 'mock', driver.mock, 'error', driver.error); races=get_next_races_apiformula1('Max Verstappen'); print('f1_races_success', races.success, 'mock', races.mock, 'count', len(races.data.get('events', [])), 'error', races.error); serp=search_sports_events_serpapi('Novak Djokovic', 'tennis'); print('serp_success', serp.success, 'mock', serp.mock, 'count', len(serp.data.get('events', [])), 'error', serp.error)"
```

Expected: either live successes or clear live provider errors with `mock False`.

- [ ] **Step 6: Restart Streamlit**

Stop the previous Streamlit session if it is still running, then run:

```bash
.venv/bin/streamlit run app.py --server.port 8503
```

Expected: app is available at `http://localhost:8503`.
