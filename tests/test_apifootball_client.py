from fanpulse_agent.agent import FanPulseAgent
from fanpulse_agent.database import FanPulseDB
from fanpulse_agent.models import SportsEntity, UserProfile
from fanpulse_agent.tools import (
    get_next_league_fixtures_apifootball,
    search_league_apifootball,
    search_soccer_fixture_apifootball,
)


def _fixture_payload():
    return {
        "fixture": {"id": 99, "date": "2999-08-20T20:00:00+00:00"},
        "league": {"id": 39, "name": "Premier League"},
        "teams": {
            "home": {"id": 42, "name": "Arsenal"},
            "away": {"id": 50, "name": "Chelsea"},
        },
    }


def test_live_soccer_team_fixtures_use_apifootball_client(monkeypatch):
    class FakeClient:
        def search_team(self, name):
            assert name == "Arsenal"
            return {"team": {"id": 42, "name": "Arsenal"}}

        def next_team_fixtures(self, team_id):
            assert team_id == 42
            return [_fixture_payload()]

    monkeypatch.setenv("APIFOOTBALL_API_KEY", "test-key")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_APIFOOTBALL", raising=False)
    monkeypatch.setattr("fanpulse_agent.tools.APIFootballClient", lambda: FakeClient())

    result = search_soccer_fixture_apifootball("Arsenal")

    assert result.success is True
    assert result.mock is False
    assert result.data["team_id"] == 42
    event = result.data["events"][0]
    assert event.title == "Arsenal vs Chelsea"
    assert event.entity_name == "Arsenal"
    assert event.metadata["provider"] == "api-football"
    assert event.metadata["fixture_id"] == 99


def test_live_league_fixtures_use_apifootball_client(monkeypatch):
    class FakeClient:
        def search_league(self, name):
            assert name == "Premier League"
            return {"league": {"id": 39, "name": "Premier League"}}

        def next_league_fixtures(self, league_id):
            assert league_id == 39
            return [_fixture_payload()]

    monkeypatch.setenv("APIFOOTBALL_API_KEY", "test-key")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_APIFOOTBALL", raising=False)
    monkeypatch.setattr("fanpulse_agent.tools.APIFootballClient", lambda: FakeClient())

    league = search_league_apifootball("Premier League")
    fixtures = get_next_league_fixtures_apifootball(39, "Premier League")

    assert league.success is True
    assert league.mock is False
    assert league.data["league_id"] == 39
    assert fixtures.success is True
    assert fixtures.mock is False
    assert fixtures.data["events"][0].entity_name == "Premier League"


def test_live_soccer_fixture_limit_error_is_not_reported_as_mock(monkeypatch):
    class FakeClient:
        last_errors = {"plan": "Free plans do not have access to the Next parameter."}

        def search_team(self, name):
            return {"team": {"id": 42, "name": "Arsenal"}}

        def next_team_fixtures(self, team_id):
            return []

    monkeypatch.setenv("APIFOOTBALL_API_KEY", "test-key")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_APIFOOTBALL", raising=False)
    monkeypatch.setattr("fanpulse_agent.tools.APIFootballClient", lambda: FakeClient())

    result = search_soccer_fixture_apifootball("Arsenal")

    assert result.success is False
    assert result.mock is False
    assert "Free plans" in result.error


def test_agent_uses_apifootball_before_sportsdb_for_soccer_team(tmp_path, monkeypatch):
    import fanpulse_agent.agent as agent_module

    calls = []

    def fake_api_football(entity_name):
        calls.append(entity_name)
        return search_soccer_fixture_apifootball(entity_name)

    class FakeClient:
        def search_team(self, name):
            return {"team": {"id": 42, "name": "Arsenal"}}

        def next_team_fixtures(self, team_id):
            return [_fixture_payload()]

    monkeypatch.setenv("APIFOOTBALL_API_KEY", "test-key")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_APIFOOTBALL", raising=False)
    monkeypatch.setattr("fanpulse_agent.tools.APIFootballClient", lambda: FakeClient())
    monkeypatch.setattr(agent_module, "search_soccer_fixture_apifootball", fake_api_football)

    agent = FanPulseAgent(FanPulseDB(str(tmp_path / "agent.db")))
    agent.current_profile = UserProfile(
        name="Mansoor",
        name_provided=True,
        timezone_provided=True,
        teams=[SportsEntity(name="Arsenal", entity_type="team", sport="soccer")],
    )

    events, unresolved = agent._collect_events(agent.current_profile)

    assert calls == ["Arsenal"]
    assert unresolved == []
    assert events[0].metadata["provider"] == "api-football"
