from fanpulse_agent.agent import FanPulseAgent
from fanpulse_agent.database import FanPulseDB
from fanpulse_agent.models import SportsEntity, UserProfile
from fanpulse_agent.tools import (
    get_next_races_apiformula1,
    get_team_games_apibasketball,
    search_driver_apiformula1,
    search_sports_events_serpapi,
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


def _formula1_race_payload():
    return {
        "id": 501,
        "competition": {"name": "Formula 1"},
        "circuit": {"name": "Silverstone Circuit"},
        "race": {"date": "2999-07-07", "time": "14:00:00+00:00"},
        "season": 2999,
        "type": "Race",
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


def test_agent_uses_official_formula1_schedule_before_provider_fallback(tmp_path, monkeypatch):
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
    assert events[0].metadata["provider"] == "official-schedule"
    assert events[0].metadata["source_parser"] == "formula1-cached-official"
    assert calls == []
