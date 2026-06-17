import pytest

from fanpulse_agent.models import SportsEntity, UserProfile
from fanpulse_agent.tools import (
    get_next_league_events_thesportsdb,
    get_next_team_events_thesportsdb,
    search_league_thesportsdb,
    search_player_thesportsdb,
    search_team_thesportsdb,
)


def test_live_team_search_uses_sportsdb_client_when_key_is_set(monkeypatch):
    class FakeClient:
        def search_team(self, name):
            assert name == "Arsenal"
            return {
                "idTeam": "133604",
                "strTeam": "Arsenal",
                "strSport": "Soccer",
                "strLeague": "English Premier League",
            }

    monkeypatch.setenv("THESPORTSDB_API_KEY", "test-key")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_SPORTSDB", raising=False)
    monkeypatch.setattr("fanpulse_agent.tools.SportsDBClient", lambda: FakeClient())

    result = search_team_thesportsdb("Arsenal")

    assert result.success is True
    assert result.mock is False
    assert result.data["team_id"] == "133604"
    assert result.data["name"] == "Arsenal"
    assert result.data["sport"] == "soccer"
    assert result.data["league"] == "English Premier League"


def test_live_team_events_map_to_digest_events(monkeypatch):
    class FakeClient:
        def next_team_events(self, team_id):
            assert team_id == "133604"
            return [
                {
                    "idEvent": "1",
                    "strEvent": "Arsenal vs Chelsea",
                    "strSport": "Soccer",
                    "strLeague": "English Premier League",
                    "strHomeTeam": "Arsenal",
                    "strAwayTeam": "Chelsea",
                    "dateEvent": "2026-06-20",
                    "strTime": "16:00:00",
                }
            ]

    monkeypatch.setenv("THESPORTSDB_API_KEY", "test-key")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_SPORTSDB", raising=False)
    monkeypatch.setattr("fanpulse_agent.tools.SportsDBClient", lambda: FakeClient())

    result = get_next_team_events_thesportsdb("133604")

    assert result.success is True
    assert result.mock is False
    event = result.data["events"][0]
    assert event.title == "Arsenal vs Chelsea"
    assert event.entity_name == "Arsenal"
    assert event.metadata["provider"] == "thesportsdb"
    assert event.metadata["event_id"] == "1"


def test_live_player_search_and_results_use_sportsdb_client(monkeypatch):
    class FakeClient:
        def search_player(self, name):
            assert name == "Bukayo Saka"
            return {
                "idPlayer": "341000",
                "strPlayer": "Bukayo Saka",
                "strSport": "Soccer",
                "strTeam": "Arsenal",
            }

        def player_results(self, player_id):
            assert player_id == "341000"
            return [
                {
                    "idEvent": "2",
                    "strEvent": "Arsenal vs Chelsea",
                    "strSport": "Soccer",
                    "strLeague": "English Premier League",
                    "dateEvent": "2026-06-20",
                    "strTime": "16:00:00",
                }
            ]

    monkeypatch.setenv("THESPORTSDB_API_KEY", "test-key")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_SPORTSDB", raising=False)
    monkeypatch.setattr("fanpulse_agent.tools.SportsDBClient", lambda: FakeClient())

    player = search_player_thesportsdb("Bukayo Saka")
    results = player.data["events"]

    assert player.success is True
    assert player.mock is False
    assert player.data["player_id"] == "341000"
    assert results[0].entity_name == "Bukayo Saka"
    assert results[0].metadata["provider"] == "thesportsdb"


def test_live_player_search_filters_historical_results(monkeypatch):
    class FakeClient:
        def search_player(self, name):
            return {
                "idPlayer": "341001",
                "strPlayer": "Novak Djokovic",
                "strSport": "Tennis",
            }

        def player_results(self, player_id):
            return [
                {
                    "idEvent": "past",
                    "strEvent": "Monte Carlo Masters",
                    "strSport": "Tennis",
                    "strLeague": "ATP",
                    "dateEvent": "2020-04-12",
                    "strTime": "13:00:00",
                },
                {
                    "idEvent": "future",
                    "strEvent": "Future Slam",
                    "strSport": "Tennis",
                    "strLeague": "ATP",
                    "dateEvent": "2999-04-12",
                    "strTime": "13:00:00",
                },
            ]

    monkeypatch.setenv("THESPORTSDB_API_KEY", "test-key")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_SPORTSDB", raising=False)
    monkeypatch.setattr("fanpulse_agent.tools.SportsDBClient", lambda: FakeClient())

    player = search_player_thesportsdb("Novak Djokovic")

    assert [event.title for event in player.data["events"]] == ["Future Slam"]


def test_live_league_search_and_events_use_sportsdb_client(monkeypatch):
    class FakeClient:
        def search_league(self, name):
            assert name == "English Premier League"
            return {
                "idLeague": "4328",
                "strLeague": "English Premier League",
                "strSport": "Soccer",
            }

        def next_league_events(self, league_id):
            assert league_id == "4328"
            return [
                {
                    "idEvent": "3",
                    "strEvent": "Arsenal vs Manchester United",
                    "strSport": "Soccer",
                    "strLeague": "English Premier League",
                    "dateEvent": "2026-06-22",
                    "strTime": "18:00:00",
                }
            ]

    monkeypatch.setenv("THESPORTSDB_API_KEY", "test-key")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_SPORTSDB", raising=False)
    monkeypatch.setattr("fanpulse_agent.tools.SportsDBClient", lambda: FakeClient())

    league = search_league_thesportsdb("English Premier League")
    events = get_next_league_events_thesportsdb("4328", "English Premier League")

    assert league.success is True
    assert league.mock is False
    assert league.data["league_id"] == "4328"
    assert events.success is True
    assert events.mock is False
    assert events.data["events"][0].entity_name == "English Premier League"


def test_user_profile_serializes_league_preferences():
    profile = UserProfile(
        name="Mansoor",
        leagues=[
            SportsEntity(
                name="English Premier League",
                entity_type="league",
                sport="soccer",
                external_id="4328",
            )
        ],
    )

    assert profile.to_dict()["leagues"][0]["name"] == "English Premier League"
