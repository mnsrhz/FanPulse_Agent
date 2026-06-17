from datetime import date, datetime
import os
import subprocess
from typing import Any, Callable, Dict, Iterable, List, Optional

import requests

from fanpulse_agent.apisports_basketball_client import APISportsBasketballClient
from fanpulse_agent.apisports_formula1_client import APISportsFormula1Client
from fanpulse_agent.apifootball_client import APIFootballClient
from fanpulse_agent.models import Digest, Event, SportsEntity, ToolResult, UserProfile
from fanpulse_agent.official_schedule import (
    events_from_source,
    source_from_search_result,
    validate_events as validate_official_events,
)
from fanpulse_agent.serpapi_client import SerpAPIClient
from fanpulse_agent.sportsdb_client import SportsDBClient
from fanpulse_agent.twilio_whatsapp_client import TwilioWhatsAppClient


SPORTSDB_SOURCE_URL = "https://www.thesportsdb.com/"
API_FOOTBALL_SOURCE_URL = "https://www.api-football.com/"
API_BASKETBALL_SOURCE_URL = "https://api-sports.io/basketball"
API_FORMULA1_SOURCE_URL = "https://api-sports.io/formula-1"
SERPAPI_SOURCE_URL = "https://serpapi.com/search-api"
WEB_SEARCH_SOURCE_URL = "https://search.example.com/fanpulse-mock"
WHATSAPP_SOURCE_URL = "https://business.whatsapp.com/"
FANPULSE_SOURCE_URL = "mock://fanpulse-agent"

SPORT_ICONS = {
    "american football": "🏈",
    "basketball": "🏀",
    "cricket": "🏏",
    "formula 1": "🏁",
    "soccer": "⚽",
    "tennis": "🎾",
}

TIMEZONE_LABELS = {
    "-07:00": "PDT",
    "+01:00": "BST",
    "+02:00": "CEST",
    "+05:30": "IST",
}


ENTITY_CATALOG: Dict[str, Dict[str, Any]] = {
    "los angeles lakers": {
        "canonical_name": "Los Angeles Lakers",
        "entity_type": "team",
        "sport": "basketball",
        "league": "NBA",
        "team_id": "lakers",
        "aliases": ("lakers", "los angeles lakers"),
        "source": SPORTSDB_SOURCE_URL,
    },
    "real madrid": {
        "canonical_name": "Real Madrid",
        "entity_type": "team",
        "sport": "soccer",
        "league": "La Liga",
        "team_id": "real-madrid",
        "fixture_id": "real-madrid",
        "aliases": ("real madrid",),
        "source": API_FOOTBALL_SOURCE_URL,
    },
    "english premier league": {
        "canonical_name": "English Premier League",
        "entity_type": "league",
        "sport": "soccer",
        "league": "English Premier League",
        "league_id": "4328",
        "team_id": "english-premier-league",
        "aliases": ("english premier league", "premier league", "epl"),
        "source": SPORTSDB_SOURCE_URL,
    },
    "san francisco 49ers": {
        "canonical_name": "San Francisco 49ers",
        "entity_type": "team",
        "sport": "american football",
        "league": "NFL",
        "team_id": "49ers",
        "aliases": ("49ers", "san francisco 49ers"),
        "source": SPORTSDB_SOURCE_URL,
    },
    "india cricket": {
        "canonical_name": "India Cricket",
        "entity_type": "team",
        "sport": "cricket",
        "league": "International Cricket",
        "team_id": "india-cricket",
        "aliases": ("india cricket", "team india"),
        "source": SPORTSDB_SOURCE_URL,
    },
    "novak djokovic": {
        "canonical_name": "Novak Djokovic",
        "entity_type": "athlete",
        "sport": "tennis",
        "league": "ATP",
        "aliases": ("novak djokovic", "djokovic"),
        "source": WEB_SEARCH_SOURCE_URL,
    },
    "max verstappen": {
        "canonical_name": "Max Verstappen",
        "entity_type": "athlete",
        "sport": "formula 1",
        "league": "Formula 1",
        "aliases": ("max verstappen", "verstappen"),
        "source": WEB_SEARCH_SOURCE_URL,
    },
}


MOCK_EVENTS: Dict[str, List[Dict[str, Any]]] = {
    "lakers": [
        {
            "title": "Los Angeles Lakers vs Golden State Warriors",
            "event_type": "game",
            "start_time": "2026-06-19T19:30:00-07:00",
            "entity_name": "Los Angeles Lakers",
            "sport": "basketball",
            "league": "NBA",
            "source_url": SPORTSDB_SOURCE_URL,
        }
    ],
    "real-madrid": [
        {
            "title": "Real Madrid vs Barcelona",
            "event_type": "fixture",
            "start_time": "2026-06-21T20:00:00+02:00",
            "entity_name": "Real Madrid",
            "sport": "soccer",
            "league": "La Liga",
            "source_url": API_FOOTBALL_SOURCE_URL,
        }
    ],
    "4328": [
        {
            "title": "Arsenal vs Manchester United",
            "event_type": "fixture",
            "start_time": "2026-06-22T18:00:00+01:00",
            "entity_name": "English Premier League",
            "sport": "soccer",
            "league": "English Premier League",
            "source_url": SPORTSDB_SOURCE_URL,
        }
    ],
    "49ers": [
        {
            "title": "San Francisco 49ers training camp report",
            "event_type": "team_update",
            "start_time": "2026-06-20T10:00:00-07:00",
            "entity_name": "San Francisco 49ers",
            "sport": "american football",
            "league": "NFL",
            "source_url": SPORTSDB_SOURCE_URL,
        }
    ],
    "india-cricket": [
        {
            "title": "India Cricket vs Australia",
            "event_type": "match",
            "start_time": "2026-06-22T14:00:00+05:30",
            "entity_name": "India Cricket",
            "sport": "cricket",
            "league": "International Cricket",
            "source_url": SPORTSDB_SOURCE_URL,
        }
    ],
    "novak-djokovic": [
        {
            "title": "Novak Djokovic grass-court tune-up",
            "event_type": "athlete_update",
            "start_time": "2026-06-18T13:00:00+01:00",
            "entity_name": "Novak Djokovic",
            "sport": "tennis",
            "league": "ATP",
            "source_url": WEB_SEARCH_SOURCE_URL,
        }
    ],
    "max-verstappen": [
        {
            "title": "Max Verstappen race weekend preview",
            "event_type": "race_preview",
            "start_time": "2026-06-20T15:00:00+02:00",
            "entity_name": "Max Verstappen",
            "sport": "formula 1",
            "league": "Formula 1",
            "source_url": WEB_SEARCH_SOURCE_URL,
        }
    ],
}


def search_team_thesportsdb(entity_name: str) -> ToolResult:
    if _sportsdb_live_enabled():
        live_result = _search_team_thesportsdb_live(entity_name)
        if live_result.success:
            return live_result

    record = _lookup_entity(entity_name)
    if not record or record["entity_type"] != "team":
        return _result(
            "thesportsdb.search_team",
            False,
            {"query": entity_name},
            SPORTSDB_SOURCE_URL,
            error=f"No mock team found for {entity_name}",
            confidence=0.2,
        )

    return _result(
        "thesportsdb.search_team",
        True,
        {
            "team_id": record["team_id"],
            "name": record["canonical_name"],
            "sport": record["sport"],
            "league": record["league"],
        },
        SPORTSDB_SOURCE_URL,
        confidence=0.98,
    )


def get_next_team_events_thesportsdb(team_id: str) -> ToolResult:
    if _sportsdb_live_enabled() and not _is_mock_identifier(team_id):
        live_result = _get_next_team_events_thesportsdb_live(team_id)
        if live_result.success:
            return live_result

    events = [_make_event(payload) for payload in MOCK_EVENTS.get(team_id, [])]
    return _result(
        "thesportsdb.get_next_team_events",
        bool(events),
        {"team_id": team_id, "events": events},
        SPORTSDB_SOURCE_URL,
        error=None if events else f"No mock events found for team_id {team_id}",
        confidence=0.95 if events else 0.25,
    )


def search_player_thesportsdb(entity_name: str) -> ToolResult:
    if _sportsdb_live_enabled():
        live_result = _search_player_thesportsdb_live(entity_name)
        if live_result.success:
            return live_result

    record = _lookup_entity(entity_name)
    event_key = _event_key(record) if record else _slug(entity_name)
    events = [_make_event(payload) for payload in MOCK_EVENTS.get(event_key, [])]
    if not record or record["entity_type"] != "athlete":
        return _result(
            "thesportsdb.search_player",
            bool(events),
            {
                "query": entity_name,
                "player_id": event_key,
                "name": entity_name,
                "sport": events[0].metadata["sport"] if events else "",
                "team": None,
                "events": events,
            },
            SPORTSDB_SOURCE_URL,
            error=None if events else f"No mock player found for {entity_name}",
            confidence=0.75 if events else 0.2,
        )

    return _result(
        "thesportsdb.search_player",
        True,
        {
            "player_id": event_key,
            "name": record["canonical_name"],
            "sport": record["sport"],
            "team": record.get("team"),
            "events": events,
        },
        SPORTSDB_SOURCE_URL,
        confidence=0.9,
    )


def search_league_thesportsdb(entity_name: str) -> ToolResult:
    if _sportsdb_live_enabled():
        live_result = _search_league_thesportsdb_live(entity_name)
        if live_result.success:
            return live_result

    record = _lookup_entity(entity_name)
    if not record or record["entity_type"] != "league":
        return _result(
            "thesportsdb.search_league",
            False,
            {"query": entity_name},
            SPORTSDB_SOURCE_URL,
            error=f"No mock league found for {entity_name}",
            confidence=0.2,
        )

    return _result(
        "thesportsdb.search_league",
        True,
        {
            "league_id": record["league_id"],
            "name": record["canonical_name"],
            "sport": record["sport"],
        },
        SPORTSDB_SOURCE_URL,
        confidence=0.9,
    )


def get_next_league_events_thesportsdb(
    league_id: str, league_name: Optional[str] = None
) -> ToolResult:
    if _sportsdb_live_enabled() and not _is_mock_identifier(league_id):
        live_result = _get_next_league_events_thesportsdb_live(league_id, league_name)
        if live_result.success:
            return live_result

    events = [_make_event(payload) for payload in MOCK_EVENTS.get(league_id, [])]
    return _result(
        "thesportsdb.get_next_league_events",
        bool(events),
        {"league_id": league_id, "events": events},
        SPORTSDB_SOURCE_URL,
        error=None if events else f"No mock league events found for league_id {league_id}",
        confidence=0.9 if events else 0.25,
    )


def search_soccer_fixture_apifootball(entity_name: str) -> ToolResult:
    if _apifootball_live_enabled():
        live_result = _search_soccer_fixture_apifootball_live(entity_name)
        return live_result

    record = _lookup_entity(entity_name)
    if not record or record["sport"] != "soccer":
        return _result(
            "api-football.search_soccer_fixture",
            False,
            {"query": entity_name, "events": []},
            API_FOOTBALL_SOURCE_URL,
            error=f"No API-Football mock fixture found for {entity_name}",
            confidence=0.2,
        )

    events = [_make_event(payload) for payload in MOCK_EVENTS[record["fixture_id"]]]
    return _result(
        "api-football.search_soccer_fixture",
        True,
        {"fixture_id": record["fixture_id"], "events": events},
        API_FOOTBALL_SOURCE_URL,
        confidence=0.94,
    )


def search_league_apifootball(entity_name: str) -> ToolResult:
    if _apifootball_live_enabled():
        live_result = _search_league_apifootball_live(entity_name)
        return live_result

    record = _lookup_entity(entity_name)
    if not record or record["entity_type"] != "league" or record["sport"] != "soccer":
        return _result(
            "api-football.search_league",
            False,
            {"query": entity_name},
            API_FOOTBALL_SOURCE_URL,
            error=f"No API-Football mock league found for {entity_name}",
            confidence=0.2,
        )
    return _result(
        "api-football.search_league",
        True,
        {
            "league_id": int(record["league_id"]),
            "name": record["canonical_name"],
            "sport": record["sport"],
        },
        API_FOOTBALL_SOURCE_URL,
        confidence=0.88,
    )


def get_next_league_fixtures_apifootball(
    league_id: int, league_name: Optional[str] = None
) -> ToolResult:
    if _apifootball_live_enabled():
        live_result = _get_next_league_fixtures_apifootball_live(league_id, league_name)
        return live_result

    events = [_make_event(payload) for payload in MOCK_EVENTS.get(str(league_id), [])]
    return _result(
        "api-football.get_next_league_fixtures",
        bool(events),
        {"league_id": league_id, "events": events},
        API_FOOTBALL_SOURCE_URL,
        error=None if events else f"No API-Football mock fixtures found for league_id {league_id}",
        confidence=0.88 if events else 0.25,
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


def get_team_games_apibasketball(
    team_id: int, team_name: Optional[str] = None
) -> ToolResult:
    if _apibasketball_live_enabled():
        return _get_team_games_apibasketball_live(team_id, team_name)
    events = [_make_event(payload) for payload in MOCK_EVENTS.get(str(team_id), [])]
    if not events and team_name:
        record = _lookup_entity(team_name)
        event_key = _event_key(record) if record else _slug(team_name)
        events = [_make_event(payload) for payload in MOCK_EVENTS.get(event_key, [])]
    return _result(
        "api-basketball.get_team_games",
        bool(events),
        {"team_id": team_id, "events": events},
        API_BASKETBALL_SOURCE_URL,
        error=None if events else f"No API-Basketball mock games found for team_id {team_id}",
        confidence=0.88 if events else 0.25,
    )


def search_league_apibasketball(entity_name: str) -> ToolResult:
    if _apibasketball_live_enabled():
        return _search_league_apibasketball_live(entity_name)
    return _result(
        "api-basketball.search_league",
        False,
        {"query": entity_name},
        API_BASKETBALL_SOURCE_URL,
        error=f"No API-Basketball mock league found for {entity_name}",
        confidence=0.2,
    )


def get_league_games_apibasketball(
    league_id: int, league_name: Optional[str] = None
) -> ToolResult:
    if _apibasketball_live_enabled():
        return _get_league_games_apibasketball_live(league_id, league_name)
    return _result(
        "api-basketball.get_league_games",
        False,
        {"league_id": league_id, "events": []},
        API_BASKETBALL_SOURCE_URL,
        error=f"No API-Basketball mock games found for league_id {league_id}",
        confidence=0.2,
    )


def search_driver_apiformula1(entity_name: str) -> ToolResult:
    if _apiformula1_live_enabled():
        return _search_driver_apiformula1_live(entity_name)
    record = _lookup_entity(entity_name)
    if not record or record["sport"] != "formula 1":
        return _result(
            "api-formula1.search_driver",
            False,
            {"query": entity_name},
            API_FORMULA1_SOURCE_URL,
            error=f"No API-Formula1 mock driver found for {entity_name}",
            confidence=0.2,
        )
    return _result(
        "api-formula1.search_driver",
        True,
        {
            "driver_id": _slug(record["canonical_name"]),
            "name": record["canonical_name"],
            "sport": record["sport"],
        },
        API_FORMULA1_SOURCE_URL,
        confidence=0.82,
    )


def get_next_races_apiformula1(entity_name: Optional[str] = None) -> ToolResult:
    if _apiformula1_live_enabled():
        return _get_next_races_apiformula1_live(entity_name)
    event_key = _slug(entity_name or "max verstappen")
    events = [_make_event(payload) for payload in MOCK_EVENTS.get(event_key, [])]
    return _result(
        "api-formula1.get_next_races",
        bool(events),
        {"entity_name": entity_name, "events": events},
        API_FORMULA1_SOURCE_URL,
        error=None if events else "No API-Formula1 mock races found.",
        confidence=0.82 if events else 0.25,
    )


def get_driver_context_apiformula1(
    driver_id: int, driver_name: Optional[str] = None
) -> ToolResult:
    if _apiformula1_live_enabled():
        return _get_driver_context_apiformula1_live(driver_id, driver_name)
    return _result(
        "api-formula1.get_driver_context",
        False,
        {"driver_id": driver_id},
        API_FORMULA1_SOURCE_URL,
        error=f"No API-Formula1 mock driver context found for {driver_id}",
        confidence=0.2,
    )


def search_sports_events_serpapi(
    entity_name: str, sport: Optional[str] = None
) -> ToolResult:
    if _serpapi_live_enabled():
        return _search_sports_events_serpapi_live(entity_name, sport)
    return _result(
        "serpapi.search_sports_events",
        False,
        {"query": entity_name, "events": []},
        SERPAPI_SOURCE_URL,
        error=f"No SerpAPI mock events found for {entity_name}",
        confidence=0.2,
    )


def search_sports_news_serpapi(entity_name: str, sport: Optional[str] = None) -> ToolResult:
    if _serpapi_live_enabled():
        return _search_sports_news_serpapi_live(entity_name, sport)
    return search_sports_events_serpapi(entity_name, sport)


def discover_official_schedule_sources(
    entity_name: str, sport: Optional[str] = None, entity_type: Optional[str] = None
) -> ToolResult:
    query = f"{entity_name} {sport or 'sports'} official schedule fixtures"
    known_sources = _known_official_schedule_sources(entity_name, sport)
    if not _serpapi_live_enabled():
        if known_sources:
            return _result(
                "official-schedule.discover_sources",
                True,
                {
                    "query": query,
                    "entity_name": entity_name,
                    "entity_type": entity_type or "",
                    "sport": sport or "",
                    "sources": known_sources,
                },
                known_sources[0]["link"],
                confidence=0.86,
                mock=False,
            )
        return _result(
            "official-schedule.discover_sources",
            False,
            {"query": query, "sources": []},
            SERPAPI_SOURCE_URL,
            error=f"No live search source enabled for official schedule discovery for {entity_name}",
            confidence=0.2,
        )

    try:
        client = SerpAPIClient()
        results = client.search(query)
    except Exception as exc:
        if known_sources:
            return _result(
                "official-schedule.discover_sources",
                True,
                {
                    "query": query,
                    "entity_name": entity_name,
                    "entity_type": entity_type or "",
                    "sport": sport or "",
                    "sources": known_sources,
                    "search_error": str(exc),
                },
                known_sources[0]["link"],
                confidence=0.82,
                mock=False,
            )
        return _result(
            "official-schedule.discover_sources",
            False,
            {"query": query, "sources": []},
            SERPAPI_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )

    sources = [
        source
        for source in (source_from_search_result(payload) for payload in results[:10])
        if source is not None
    ]
    existing_links = {source["link"] for source in sources}
    sources.extend(source for source in known_sources if source["link"] not in existing_links)
    return _result(
        "official-schedule.discover_sources",
        bool(sources),
        {
            "query": query,
            "entity_name": entity_name,
            "entity_type": entity_type or "",
            "sport": sport or "",
            "sources": sources,
        },
        sources[0]["link"] if sources else SERPAPI_SOURCE_URL,
        error=None if sources else f"No trusted official schedule sources found for {entity_name}",
        confidence=0.86 if sources else 0.25,
        mock=False,
    )


def _known_official_schedule_sources(
    entity_name: str, sport: Optional[str] = None
) -> List[Dict[str, Any]]:
    normalized = f"{entity_name} {sport or ''}".lower()
    if "formula 1" in normalized or "f1" in normalized or "verstappen" in normalized:
        year = date.today().year
        return [
            {
                "title": f"F1 Schedule {year}",
                "link": f"https://www.formula1.com/en/racing/{year}",
                "snippet": "Official Formula 1 race calendar.",
                "date": None,
                "domain": "formula1.com",
            }
        ]
    return []


def extract_official_schedule_events(
    entity_name: str, sport: Optional[str], sources: List[Dict[str, Any]]
) -> ToolResult:
    enriched_sources = [_source_with_page_text(source) for source in sources]
    events = [
        event
        for source in enriched_sources
        for event in events_from_source(entity_name, sport or "", source)
    ]
    source_url = sources[0]["link"] if sources else FANPULSE_SOURCE_URL
    return _result(
        "official-schedule.extract_events",
        bool(events),
        {"entity_name": entity_name, "sport": sport or "", "events": events},
        source_url,
        error=None
        if events
        else f"No confident future events could be extracted for {entity_name}",
        confidence=0.84 if events else 0.25,
        mock=False,
    )


def _source_with_page_text(source: Dict[str, Any]) -> Dict[str, Any]:
    if source.get("date") or source.get("page_text"):
        return source
    link = str(source.get("link") or "")
    if not link:
        return source
    enriched = dict(source)
    try:
        response = requests.get(
            link,
            headers={"User-Agent": "FanPulseAI/0.1 (+https://fanpulse.local)"},
            timeout=8,
        )
        response.raise_for_status()
        enriched["page_text"] = response.text[:1_000_000]
    except Exception as exc:
        enriched["page_fetch_error"] = str(exc)
        curl_text = _fetch_page_with_curl(link)
        if curl_text:
            enriched["page_text"] = curl_text[:1_000_000]
    return enriched


def _fetch_page_with_curl(link: str) -> str:
    try:
        completed = subprocess.run(
            ["curl", "-L", "--max-time", "10", "--silent", "--show-error", link],
            check=False,
            capture_output=True,
            text=True,
            timeout=12,
        )
    except Exception:
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout


def validate_official_schedule_events(events: List[Event]) -> ToolResult:
    validated = validate_official_events(events)
    source_url = validated[0].source_url if validated else FANPULSE_SOURCE_URL
    return _result(
        "official-schedule.validate_events",
        bool(validated),
        {"events": validated},
        source_url or FANPULSE_SOURCE_URL,
        error=None if validated else "No future official events with source URLs passed validation",
        confidence=0.88 if validated else 0.25,
        mock=False,
    )


def web_search_event_source(entity_name: str) -> ToolResult:
    if _sportsdb_live_enabled():
        player_result = _search_player_thesportsdb_live(entity_name)
        if player_result.success:
            return player_result

    record = _lookup_entity(entity_name)
    event_key = _event_key(record) if record else _slug(entity_name)
    events = [_make_event(payload) for payload in MOCK_EVENTS.get(event_key, [])]
    return _result(
        "web.search_event_source",
        bool(events),
        {"query": entity_name, "events": events},
        WEB_SEARCH_SOURCE_URL,
        error=None if events else f"No mock web event found for {entity_name}",
        confidence=0.9 if events else 0.25,
    )


def normalize_sports_entity(entity_name: str) -> ToolResult:
    if _sportsdb_live_enabled():
        live_team = _search_team_thesportsdb_live(entity_name)
        if live_team.success:
            entity = SportsEntity(
                name=live_team.data["name"],
                entity_type="team",
                sport=live_team.data["sport"],
                source_text=entity_name,
                confidence=0.96,
                league=live_team.data["league"],
                external_id=live_team.data["team_id"],
            )
            return _result(
                "fanpulse.normalize_sports_entity",
                True,
                {"entity": entity, "canonical_name": entity.name},
                SPORTSDB_SOURCE_URL,
                confidence=0.96,
                mock=False,
            )

    record = _lookup_entity(entity_name)
    if not record:
        return _result(
            "fanpulse.normalize_sports_entity",
            False,
            {"query": entity_name},
            FANPULSE_SOURCE_URL,
            error=f"No mock entity found for {entity_name}",
            confidence=0.2,
        )

    entity = SportsEntity(
        name=record["canonical_name"],
        entity_type=record["entity_type"],
        sport=record["sport"],
        source_text=entity_name,
        confidence=0.96,
        league=record["league"],
        external_id=record.get("team_id"),
    )
    return _result(
        "fanpulse.normalize_sports_entity",
        True,
        {"entity": entity, "canonical_name": entity.name},
        FANPULSE_SOURCE_URL,
        confidence=0.96,
    )


def rank_events(events: List[Event], user_preferences: UserProfile) -> ToolResult:
    events = [event for event in events if is_upcoming_event(event)]
    preferred_sports = set(user_preferences.sports or user_preferences.favorite_sports)
    ranked = sorted(
        events,
        key=lambda event: (
            0 if not preferred_sports or event.metadata.get("sport") in preferred_sports else 1,
            event.start_time or "",
            event.title,
        ),
    )
    return _result(
        "fanpulse.rank_events",
        True,
        {"events": ranked, "ranked_count": len(ranked)},
        FANPULSE_SOURCE_URL,
        confidence=0.88,
    )


def generate_digest(events: List[Event], user_profile: UserProfile) -> ToolResult:
    user_id = user_profile.user_id or user_profile.name.lower().replace(" ", "-")
    digest = Digest(
        user_id=user_id,
        title=f"FanPulse Weekly Digest for {user_profile.name}",
        events=events,
        summary=_summarize_events(events),
    )
    return _result(
        "fanpulse.generate_digest",
        True,
        {"digest": digest, "event_count": len(events)},
        FANPULSE_SOURCE_URL,
        confidence=0.9,
    )


def send_whatsapp_digest(phone_number: str, digest_text: str) -> ToolResult:
    if _twilio_live_enabled():
        return _send_whatsapp_digest_twilio_live(phone_number, digest_text)
    return _result(
        "whatsapp.send_digest",
        True,
        {
            "phone_number": phone_number,
            "message_preview": digest_text[:160],
            "sent": False,
            "delivery_status": "mocked_not_sent",
        },
        WHATSAPP_SOURCE_URL,
        confidence=1.0,
    )


def save_user_preferences(user_profile: UserProfile) -> ToolResult:
    user_id = user_profile.user_id or user_profile.name.lower().replace(" ", "-")
    return _result(
        "fanpulse.save_user_preferences",
        True,
        {"user_id": user_id, "profile": user_profile},
        FANPULSE_SOURCE_URL,
        confidence=0.93,
    )


def save_digest_history(user_id: str, digest: Digest) -> ToolResult:
    return _result(
        "fanpulse.save_digest_history",
        True,
        {"user_id": user_id, "digest": digest, "saved": True},
        FANPULSE_SOURCE_URL,
        confidence=0.93,
    )


TOOL_REGISTRY: Dict[str, Callable[..., ToolResult]] = {
    "thesportsdb.search_team": search_team_thesportsdb,
    "thesportsdb.get_next_team_events": get_next_team_events_thesportsdb,
    "thesportsdb.search_player": search_player_thesportsdb,
    "thesportsdb.search_league": search_league_thesportsdb,
    "thesportsdb.get_next_league_events": get_next_league_events_thesportsdb,
    "api-football.search_soccer_fixture": search_soccer_fixture_apifootball,
    "api-football.search_league": search_league_apifootball,
    "api-football.get_next_league_fixtures": get_next_league_fixtures_apifootball,
    "api-basketball.search_team": search_team_apibasketball,
    "api-basketball.get_team_games": get_team_games_apibasketball,
    "api-basketball.search_league": search_league_apibasketball,
    "api-basketball.get_league_games": get_league_games_apibasketball,
    "api-formula1.search_driver": search_driver_apiformula1,
    "api-formula1.get_next_races": get_next_races_apiformula1,
    "api-formula1.get_driver_context": get_driver_context_apiformula1,
    "serpapi.search_sports_events": search_sports_events_serpapi,
    "serpapi.search_sports_news": search_sports_news_serpapi,
    "official-schedule.discover_sources": discover_official_schedule_sources,
    "official-schedule.extract_events": extract_official_schedule_events,
    "official-schedule.validate_events": validate_official_schedule_events,
    "web.search_event_source": web_search_event_source,
    "fanpulse.normalize_sports_entity": normalize_sports_entity,
    "fanpulse.rank_events": rank_events,
    "fanpulse.generate_digest": generate_digest,
    "whatsapp.send_digest": send_whatsapp_digest,
    "fanpulse.save_user_preferences": save_user_preferences,
    "fanpulse.save_digest_history": save_digest_history,
}


def _result(
    tool_name: str,
    success: bool,
    data: Any,
    source_url: str,
    error: Optional[str] = None,
    confidence: float = 0.9,
    mock: bool = True,
) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        success=success,
        data=data,
        source_url=source_url,
        error=error,
        confidence=confidence,
        mock=mock,
    )


def _lookup_entity(entity_name: str) -> Optional[Dict[str, Any]]:
    query = entity_name.strip().lower()
    for record in ENTITY_CATALOG.values():
        if query in record["aliases"]:
            return record
    return ENTITY_CATALOG.get(query)


def _sportsdb_live_enabled() -> bool:
    return bool(
        os.environ.get("THESPORTSDB_API_KEY")
        and os.environ.get("FANPULSE_DISABLE_LIVE_SPORTSDB") != "1"
    )


def _apifootball_live_enabled() -> bool:
    return bool(
        os.environ.get("APIFOOTBALL_API_KEY")
        and os.environ.get("FANPULSE_DISABLE_LIVE_APIFOOTBALL") != "1"
    )


def _apibasketball_live_enabled() -> bool:
    return bool(
        (os.environ.get("APISPORTS_BASKETBALL_API_KEY") or os.environ.get("APIFOOTBALL_API_KEY"))
        and os.environ.get("FANPULSE_DISABLE_LIVE_APISPORTS_BASKETBALL") != "1"
    )


def _apiformula1_live_enabled() -> bool:
    return bool(
        (os.environ.get("APISPORTS_FORMULA1_API_KEY") or os.environ.get("APIFOOTBALL_API_KEY"))
        and os.environ.get("FANPULSE_DISABLE_LIVE_APISPORTS_FORMULA1") != "1"
    )


def _serpapi_live_enabled() -> bool:
    return bool(
        os.environ.get("SERPAPI_API_KEY")
        and os.environ.get("FANPULSE_DISABLE_LIVE_SERPAPI") != "1"
    )


def _twilio_live_enabled() -> bool:
    return bool(
        os.environ.get("TWILIO_ACCOUNT_SID")
        and os.environ.get("TWILIO_AUTH_TOKEN")
        and os.environ.get("TWILIO_WHATSAPP_FROM")
        and os.environ.get("FANPULSE_DISABLE_LIVE_TWILIO") != "1"
    )


def _send_whatsapp_digest_twilio_live(phone_number: str, digest_text: str) -> ToolResult:
    try:
        payload = TwilioWhatsAppClient().send_message(phone_number, digest_text)
    except Exception as exc:
        return _result(
            "whatsapp.send_digest",
            False,
            {
                "phone_number": phone_number,
                "message_preview": digest_text[:160],
                "sent": False,
                "delivery_status": "failed",
            },
            WHATSAPP_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )
    status = str(payload.get("status") or "queued")
    return _result(
        "whatsapp.send_digest",
        True,
        {
            "phone_number": phone_number,
            "message_preview": digest_text[:160],
            "sent": True,
            "delivery_status": status,
            "message_sid": payload.get("sid"),
        },
        WHATSAPP_SOURCE_URL,
        confidence=0.98,
        mock=False,
    )


def _search_soccer_fixture_apifootball_live(entity_name: str) -> ToolResult:
    try:
        client = APIFootballClient()
        team = client.search_team(entity_name)
        fixtures_payload = (
            client.next_team_fixtures(int(team["team"]["id"])) if team else []
        )
    except Exception as exc:
        return _result(
            "api-football.search_soccer_fixture",
            False,
            {"query": entity_name, "events": []},
            API_FOOTBALL_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )
    if not team:
        return _result(
            "api-football.search_soccer_fixture",
            False,
            {"query": entity_name, "events": []},
            API_FOOTBALL_SOURCE_URL,
            error=f"No API-Football team found for {entity_name}",
            confidence=0.2,
            mock=False,
        )
    team_name = str(team.get("team", {}).get("name") or entity_name)
    team_id = int(team.get("team", {}).get("id") or 0)
    events = [
        _make_apifootball_event(payload, entity_name=team_name, event_type="fixture")
        for payload in fixtures_payload
    ]
    events = [event for event in events if is_upcoming_event(event)]
    provider_error = _apifootball_error_message(getattr(client, "last_errors", None))
    return _result(
        "api-football.search_soccer_fixture",
        bool(events),
        {"team_id": team_id, "name": team_name, "events": events},
        API_FOOTBALL_SOURCE_URL,
        error=(
            None
            if events
            else provider_error
            or f"No upcoming API-Football fixtures found for {team_name}"
        ),
        confidence=0.93 if events else 0.25,
        mock=False,
    )


def _search_league_apifootball_live(entity_name: str) -> ToolResult:
    try:
        league = APIFootballClient().search_league(entity_name)
    except Exception as exc:
        return _result(
            "api-football.search_league",
            False,
            {"query": entity_name},
            API_FOOTBALL_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )
    if not league:
        return _result(
            "api-football.search_league",
            False,
            {"query": entity_name},
            API_FOOTBALL_SOURCE_URL,
            error=f"No API-Football league found for {entity_name}",
            confidence=0.2,
            mock=False,
        )
    return _result(
        "api-football.search_league",
        True,
        {
            "league_id": int(league.get("league", {}).get("id") or 0),
            "name": str(league.get("league", {}).get("name") or entity_name),
            "sport": "soccer",
        },
        API_FOOTBALL_SOURCE_URL,
        confidence=0.9,
        mock=False,
    )


def _get_next_league_fixtures_apifootball_live(
    league_id: int, league_name: Optional[str]
) -> ToolResult:
    try:
        client = APIFootballClient()
        fixtures_payload = client.next_league_fixtures(int(league_id))
    except Exception as exc:
        return _result(
            "api-football.get_next_league_fixtures",
            False,
            {"league_id": league_id, "events": []},
            API_FOOTBALL_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )
    entity_name = league_name or str(league_id)
    events = [
        _make_apifootball_event(payload, entity_name=entity_name, event_type="fixture")
        for payload in fixtures_payload
    ]
    events = [event for event in events if is_upcoming_event(event)]
    provider_error = _apifootball_error_message(getattr(client, "last_errors", None))
    return _result(
        "api-football.get_next_league_fixtures",
        bool(events),
        {"league_id": league_id, "events": events},
        API_FOOTBALL_SOURCE_URL,
        error=(
            None
            if events
            else provider_error
            or f"No upcoming API-Football fixtures found for league_id {league_id}"
        ),
        confidence=0.92 if events else 0.25,
        mock=False,
    )


def _apifootball_error_message(errors: Any) -> Optional[str]:
    if isinstance(errors, dict) and errors:
        return "; ".join(f"{key}: {value}" for key, value in errors.items())
    if isinstance(errors, list) and errors:
        return "; ".join(str(error) for error in errors)
    if isinstance(errors, str) and errors:
        return errors
    return None


def _provider_error_message(errors: Any) -> Optional[str]:
    return _apifootball_error_message(errors)


def _search_team_apibasketball_live(entity_name: str) -> ToolResult:
    try:
        client = APISportsBasketballClient()
        team = client.search_team(entity_name)
    except Exception as exc:
        return _result(
            "api-basketball.search_team",
            False,
            {"query": entity_name},
            API_BASKETBALL_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )
    if not team:
        return _result(
            "api-basketball.search_team",
            False,
            {"query": entity_name},
            API_BASKETBALL_SOURCE_URL,
            error=_provider_error_message(getattr(client, "last_errors", None))
            or f"No API-Basketball team found for {entity_name}",
            confidence=0.2,
            mock=False,
        )
    return _result(
        "api-basketball.search_team",
        True,
        {
            "team_id": int(team.get("id") or 0),
            "name": str(team.get("name") or entity_name),
            "sport": "basketball",
            "league": team.get("league") or team.get("country"),
        },
        API_BASKETBALL_SOURCE_URL,
        confidence=0.9,
        mock=False,
    )


def _get_team_games_apibasketball_live(
    team_id: int, team_name: Optional[str]
) -> ToolResult:
    try:
        client = APISportsBasketballClient()
        games_payload = client.next_team_games(int(team_id))
    except Exception as exc:
        return _result(
            "api-basketball.get_team_games",
            False,
            {"team_id": team_id, "events": []},
            API_BASKETBALL_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )
    entity_name = team_name or str(team_id)
    events = [
        _make_apibasketball_event(payload, entity_name=entity_name)
        for payload in games_payload
    ]
    events = [event for event in events if is_upcoming_event(event)]
    return _result(
        "api-basketball.get_team_games",
        bool(events),
        {"team_id": team_id, "events": events},
        API_BASKETBALL_SOURCE_URL,
        error=None
        if events
        else _provider_error_message(getattr(client, "last_errors", None))
        or f"No upcoming API-Basketball games found for {entity_name}",
        confidence=0.9 if events else 0.25,
        mock=False,
    )


def _search_league_apibasketball_live(entity_name: str) -> ToolResult:
    try:
        client = APISportsBasketballClient()
        league = client.search_league(entity_name)
    except Exception as exc:
        return _result(
            "api-basketball.search_league",
            False,
            {"query": entity_name},
            API_BASKETBALL_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )
    if not league:
        return _result(
            "api-basketball.search_league",
            False,
            {"query": entity_name},
            API_BASKETBALL_SOURCE_URL,
            error=_provider_error_message(getattr(client, "last_errors", None))
            or f"No API-Basketball league found for {entity_name}",
            confidence=0.2,
            mock=False,
        )
    return _result(
        "api-basketball.search_league",
        True,
        {
            "league_id": int(league.get("id") or 0),
            "name": str(league.get("name") or entity_name),
            "sport": "basketball",
        },
        API_BASKETBALL_SOURCE_URL,
        confidence=0.85,
        mock=False,
    )


def _get_league_games_apibasketball_live(
    league_id: int, league_name: Optional[str]
) -> ToolResult:
    try:
        client = APISportsBasketballClient()
        games_payload = client.next_league_games(int(league_id))
    except Exception as exc:
        return _result(
            "api-basketball.get_league_games",
            False,
            {"league_id": league_id, "events": []},
            API_BASKETBALL_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )
    entity_name = league_name or str(league_id)
    events = [
        _make_apibasketball_event(payload, entity_name=entity_name)
        for payload in games_payload
    ]
    events = [event for event in events if is_upcoming_event(event)]
    return _result(
        "api-basketball.get_league_games",
        bool(events),
        {"league_id": league_id, "events": events},
        API_BASKETBALL_SOURCE_URL,
        error=None
        if events
        else _provider_error_message(getattr(client, "last_errors", None))
        or f"No upcoming API-Basketball games found for league_id {league_id}",
        confidence=0.85 if events else 0.25,
        mock=False,
    )


def _search_driver_apiformula1_live(entity_name: str) -> ToolResult:
    try:
        client = APISportsFormula1Client()
        driver = client.search_driver(entity_name)
    except Exception as exc:
        return _result(
            "api-formula1.search_driver",
            False,
            {"query": entity_name},
            API_FORMULA1_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )
    if not driver:
        return _result(
            "api-formula1.search_driver",
            False,
            {"query": entity_name},
            API_FORMULA1_SOURCE_URL,
            error=_provider_error_message(getattr(client, "last_errors", None))
            or f"No API-Formula1 driver found for {entity_name}",
            confidence=0.2,
            mock=False,
        )
    return _result(
        "api-formula1.search_driver",
        True,
        {
            "driver_id": int(driver.get("id") or 0),
            "name": str(driver.get("name") or entity_name),
            "sport": "formula 1",
        },
        API_FORMULA1_SOURCE_URL,
        confidence=0.9,
        mock=False,
    )


def _get_next_races_apiformula1_live(entity_name: Optional[str]) -> ToolResult:
    try:
        client = APISportsFormula1Client()
        races_payload = client.next_races()
    except Exception as exc:
        return _result(
            "api-formula1.get_next_races",
            False,
            {"entity_name": entity_name, "events": []},
            API_FORMULA1_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )
    events = [
        _make_apiformula1_event(payload, entity_name=entity_name or "Formula 1")
        for payload in races_payload
    ]
    events = [event for event in events if is_upcoming_event(event)]
    return _result(
        "api-formula1.get_next_races",
        bool(events),
        {"entity_name": entity_name, "events": events},
        API_FORMULA1_SOURCE_URL,
        error=None
        if events
        else _provider_error_message(getattr(client, "last_errors", None))
        or "No upcoming API-Formula1 races found.",
        confidence=0.88 if events else 0.25,
        mock=False,
    )


def _get_driver_context_apiformula1_live(
    driver_id: int, driver_name: Optional[str]
) -> ToolResult:
    try:
        client = APISportsFormula1Client()
        rankings = client.driver_rankings(int(driver_id))
    except Exception as exc:
        return _result(
            "api-formula1.get_driver_context",
            False,
            {"driver_id": driver_id},
            API_FORMULA1_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )
    return _result(
        "api-formula1.get_driver_context",
        bool(rankings),
        {"driver_id": driver_id, "driver_name": driver_name, "rankings": rankings},
        API_FORMULA1_SOURCE_URL,
        error=None
        if rankings
        else _provider_error_message(getattr(client, "last_errors", None))
        or f"No API-Formula1 context found for {driver_name or driver_id}",
        confidence=0.8 if rankings else 0.25,
        mock=False,
    )


def _search_sports_events_serpapi_live(
    entity_name: str, sport: Optional[str]
) -> ToolResult:
    query = f"{entity_name} {sport or 'sports'} upcoming schedule"
    try:
        client = SerpAPIClient()
        results = client.search(query)
    except Exception as exc:
        return _result(
            "serpapi.search_sports_events",
            False,
            {"query": query, "events": []},
            SERPAPI_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )
    events = [
        _make_serpapi_event(payload, entity_name=entity_name, sport=sport)
        for payload in results[:5]
    ]
    return _result(
        "serpapi.search_sports_events",
        bool(events),
        {"query": query, "events": events},
        SERPAPI_SOURCE_URL,
        error=None
        if events
        else _provider_error_message(getattr(client, "last_errors", None))
        or f"No SerpAPI event results found for {entity_name}",
        confidence=0.7 if events else 0.2,
        mock=False,
    )


def _search_sports_news_serpapi_live(
    entity_name: str, sport: Optional[str]
) -> ToolResult:
    query = f"{entity_name} {sport or 'sports'} latest news"
    try:
        client = SerpAPIClient()
        results = client.search(query)
    except Exception as exc:
        return _result(
            "serpapi.search_sports_news",
            False,
            {"query": query, "events": []},
            SERPAPI_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )
    events = [
        _make_serpapi_event(payload, entity_name=entity_name, sport=sport)
        for payload in results[:5]
    ]
    return _result(
        "serpapi.search_sports_news",
        bool(events),
        {"query": query, "events": events},
        SERPAPI_SOURCE_URL,
        error=None
        if events
        else _provider_error_message(getattr(client, "last_errors", None))
        or f"No SerpAPI news results found for {entity_name}",
        confidence=0.65 if events else 0.2,
        mock=False,
    )


def _search_team_thesportsdb_live(entity_name: str) -> ToolResult:
    try:
        team = SportsDBClient().search_team(entity_name)
    except Exception as exc:
        return _result(
            "thesportsdb.search_team",
            False,
            {"query": entity_name},
            SPORTSDB_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )
    if not team:
        return _result(
            "thesportsdb.search_team",
            False,
            {"query": entity_name},
            SPORTSDB_SOURCE_URL,
            error=f"No SportsDB team found for {entity_name}",
            confidence=0.2,
            mock=False,
        )
    return _result(
        "thesportsdb.search_team",
        True,
        {
            "team_id": str(team.get("idTeam") or ""),
            "name": str(team.get("strTeam") or entity_name),
            "sport": _normalize_sport(team.get("strSport")),
            "league": team.get("strLeague"),
        },
        SPORTSDB_SOURCE_URL,
        confidence=0.95,
        mock=False,
    )


def _get_next_team_events_thesportsdb_live(team_id: str) -> ToolResult:
    try:
        events_payload = SportsDBClient().next_team_events(team_id)
    except Exception as exc:
        return _result(
            "thesportsdb.get_next_team_events",
            False,
            {"team_id": team_id, "events": []},
            SPORTSDB_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )
    events = [
        _make_sportsdb_event(payload, entity_name=_event_entity_name(payload), event_type="game")
        for payload in events_payload
    ]
    return _result(
        "thesportsdb.get_next_team_events",
        bool(events),
        {"team_id": team_id, "events": events},
        SPORTSDB_SOURCE_URL,
        error=None if events else f"No SportsDB events found for team_id {team_id}",
        confidence=0.9 if events else 0.25,
        mock=False,
    )


def _search_player_thesportsdb_live(entity_name: str) -> ToolResult:
    try:
        client = SportsDBClient()
        player = client.search_player(entity_name)
        events_payload = client.player_results(str(player.get("idPlayer"))) if player else []
    except Exception as exc:
        return _result(
            "thesportsdb.search_player",
            False,
            {"query": entity_name, "events": []},
            SPORTSDB_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )
    if not player:
        return _result(
            "thesportsdb.search_player",
            False,
            {"query": entity_name, "events": []},
            SPORTSDB_SOURCE_URL,
            error=f"No SportsDB player found for {entity_name}",
            confidence=0.2,
            mock=False,
        )
    player_name = str(player.get("strPlayer") or entity_name)
    events = [
        _make_sportsdb_event(payload, entity_name=player_name, event_type="athlete_update")
        for payload in events_payload
    ]
    events = [event for event in events if is_upcoming_event(event)]
    return _result(
        "thesportsdb.search_player",
        True,
        {
            "player_id": str(player.get("idPlayer") or ""),
            "name": player_name,
            "sport": _normalize_sport(player.get("strSport")),
            "team": player.get("strTeam"),
            "events": events,
        },
        SPORTSDB_SOURCE_URL,
        confidence=0.88 if events else 0.72,
        mock=False,
    )


def _search_league_thesportsdb_live(entity_name: str) -> ToolResult:
    try:
        league = SportsDBClient().search_league(entity_name)
    except Exception as exc:
        return _result(
            "thesportsdb.search_league",
            False,
            {"query": entity_name},
            SPORTSDB_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )
    if not league:
        return _result(
            "thesportsdb.search_league",
            False,
            {"query": entity_name},
            SPORTSDB_SOURCE_URL,
            error=f"No SportsDB league found for {entity_name}",
            confidence=0.2,
            mock=False,
        )
    return _result(
        "thesportsdb.search_league",
        True,
        {
            "league_id": str(league.get("idLeague") or ""),
            "name": str(league.get("strLeague") or entity_name),
            "sport": _normalize_sport(league.get("strSport")),
        },
        SPORTSDB_SOURCE_URL,
        confidence=0.9,
        mock=False,
    )


def _get_next_league_events_thesportsdb_live(
    league_id: str, league_name: Optional[str]
) -> ToolResult:
    try:
        events_payload = SportsDBClient().next_league_events(league_id)
    except Exception as exc:
        return _result(
            "thesportsdb.get_next_league_events",
            False,
            {"league_id": league_id, "events": []},
            SPORTSDB_SOURCE_URL,
            error=str(exc),
            confidence=0.2,
            mock=False,
        )
    entity_name = league_name or league_id
    events = [
        _make_sportsdb_event(payload, entity_name=entity_name, event_type="fixture")
        for payload in events_payload
    ]
    return _result(
        "thesportsdb.get_next_league_events",
        bool(events),
        {"league_id": league_id, "events": events},
        SPORTSDB_SOURCE_URL,
        error=None if events else f"No SportsDB league events found for {league_id}",
        confidence=0.9 if events else 0.25,
        mock=False,
    )


def _make_sportsdb_event(
    payload: Dict[str, Any],
    entity_name: str,
    event_type: str,
) -> Event:
    sport = _normalize_sport(payload.get("strSport"))
    league = payload.get("strLeague") or "SportsDB"
    title = payload.get("strEvent") or entity_name
    start_time = _sportsdb_datetime(payload)
    sport_icon = SPORT_ICONS.get(sport, "🏟️")
    event = Event(
        title=title,
        event_type=event_type,
        start_time=start_time,
        sport_icon=sport_icon,
        opponent=_opponent_from_title(title, entity_name),
        display_time=_display_time(start_time),
        confidence=0.9,
        mock=False,
        incomplete=False,
        entities=[
            SportsEntity(
                name=entity_name,
                entity_type="athlete" if event_type == "athlete_update" else "team",
                sport=sport,
                league=league,
            )
        ],
        source_url=SPORTSDB_SOURCE_URL,
        metadata={
            "sport": sport,
            "league": league,
            "provider": "thesportsdb",
            "event_id": payload.get("idEvent"),
            "confidence": 0.9,
            "mock": False,
            "incomplete": False,
            "sport_icon": sport_icon,
            "opponent": _opponent_from_title(title, entity_name),
            "display_time": _display_time(start_time),
        },
        entity_name=entity_name,
    )
    return event


def _make_apifootball_event(
    payload: Dict[str, Any],
    entity_name: str,
    event_type: str,
) -> Event:
    fixture = payload.get("fixture") or {}
    teams = payload.get("teams") or {}
    league_payload = payload.get("league") or {}
    home = (teams.get("home") or {}).get("name")
    away = (teams.get("away") or {}).get("name")
    title = f"{home} vs {away}" if home and away else entity_name
    start_time = fixture.get("date")
    sport = "soccer"
    league = league_payload.get("name") or "Soccer"
    sport_icon = SPORT_ICONS.get(sport, "⚽")
    opponent = _opponent_from_title(title, entity_name)
    display_time = _display_time(start_time)
    return Event(
        title=title,
        event_type=event_type,
        start_time=start_time,
        sport_icon=sport_icon,
        opponent=opponent,
        display_time=display_time,
        confidence=0.93,
        mock=False,
        incomplete=False,
        entities=[
            SportsEntity(
                name=entity_name,
                entity_type="team",
                sport=sport,
                league=league,
            )
        ],
        source_url=API_FOOTBALL_SOURCE_URL,
        metadata={
            "sport": sport,
            "league": league,
            "provider": "api-football",
            "fixture_id": fixture.get("id"),
            "confidence": 0.93,
            "mock": False,
            "incomplete": False,
            "sport_icon": sport_icon,
            "opponent": opponent,
            "display_time": display_time,
        },
        entity_name=entity_name,
    )


def _make_apibasketball_event(payload: Dict[str, Any], entity_name: str) -> Event:
    teams = payload.get("teams") or {}
    league_payload = payload.get("league") or {}
    home = (teams.get("home") or {}).get("name")
    away = (teams.get("away") or {}).get("name")
    title = f"{home} vs {away}" if home and away else entity_name
    start_time = payload.get("date")
    sport = "basketball"
    league = league_payload.get("name") or "Basketball"
    sport_icon = SPORT_ICONS.get(sport, "🏀")
    opponent = _opponent_from_title(title, entity_name)
    display_time = _display_time(start_time)
    return Event(
        title=title,
        event_type="game",
        start_time=start_time,
        sport_icon=sport_icon,
        opponent=opponent,
        display_time=display_time,
        confidence=0.9,
        mock=False,
        incomplete=False,
        entities=[
            SportsEntity(
                name=entity_name,
                entity_type="team",
                sport=sport,
                league=league,
            )
        ],
        source_url=API_BASKETBALL_SOURCE_URL,
        metadata={
            "sport": sport,
            "league": league,
            "provider": "api-basketball",
            "game_id": payload.get("id"),
            "confidence": 0.9,
            "mock": False,
            "incomplete": False,
            "sport_icon": sport_icon,
            "opponent": opponent,
            "display_time": display_time,
        },
        entity_name=entity_name,
    )


def _make_apiformula1_event(payload: Dict[str, Any], entity_name: str) -> Event:
    circuit = payload.get("circuit") or {}
    competition = payload.get("competition") or {}
    race = payload.get("race") or {}
    circuit_name = circuit.get("name") or "Formula 1 circuit"
    title = f"Formula 1 at {circuit_name}"
    start_time = _formula1_datetime(race)
    sport = "formula 1"
    league = competition.get("name") or "Formula 1"
    sport_icon = SPORT_ICONS.get(sport, "🏁")
    display_time = _display_time(start_time)
    return Event(
        title=title,
        event_type="race",
        start_time=start_time,
        sport_icon=sport_icon,
        opponent=None,
        display_time=display_time,
        confidence=0.88,
        mock=False,
        incomplete=False,
        entities=[
            SportsEntity(
                name=entity_name,
                entity_type="athlete",
                sport=sport,
                league=league,
            )
        ],
        source_url=API_FORMULA1_SOURCE_URL,
        metadata={
            "sport": sport,
            "league": league,
            "provider": "api-formula1",
            "race_id": payload.get("id"),
            "season": payload.get("season"),
            "confidence": 0.88,
            "mock": False,
            "incomplete": False,
            "sport_icon": sport_icon,
            "opponent": None,
            "display_time": display_time,
        },
        entity_name=entity_name,
    )


def _make_serpapi_event(
    payload: Dict[str, Any],
    entity_name: str,
    sport: Optional[str],
) -> Event:
    normalized_sport = (sport or "sport").strip().lower()
    title = str(payload.get("title") or entity_name)
    start_time = payload.get("date")
    source_url = str(payload.get("link") or SERPAPI_SOURCE_URL)
    league = normalized_sport.title() if normalized_sport != "sport" else "Sports"
    sport_icon = SPORT_ICONS.get(normalized_sport, "🏟️")
    display_time = _display_time(start_time)
    return Event(
        title=title,
        event_type="search_result",
        start_time=start_time,
        sport_icon=sport_icon,
        opponent=None,
        display_time=display_time,
        confidence=0.7,
        mock=False,
        incomplete=True,
        entities=[
            SportsEntity(
                name=entity_name,
                entity_type="athlete",
                sport=normalized_sport,
                league=league,
            )
        ],
        source_url=source_url,
        metadata={
            "sport": normalized_sport,
            "league": league,
            "provider": "serpapi",
            "serpapi_result_id": payload.get("position") or payload.get("result_id"),
            "snippet": payload.get("snippet"),
            "confidence": 0.7,
            "mock": False,
            "incomplete": True,
            "sport_icon": sport_icon,
            "opponent": None,
            "display_time": display_time,
        },
        entity_name=entity_name,
    )


def _formula1_datetime(race: Dict[str, Any]) -> Optional[str]:
    date_value = race.get("date")
    time_value = race.get("time")
    if not date_value:
        return None
    if time_value:
        return f"{date_value}T{str(time_value).strip()}"
    return str(date_value)


def _sportsdb_datetime(payload: Dict[str, Any]) -> Optional[str]:
    date = payload.get("dateEvent")
    time = payload.get("strTime")
    if not date:
        return None
    if time:
        return f"{date}T{str(time).strip()}"
    return str(date)


def _event_entity_name(payload: Dict[str, Any]) -> str:
    return str(payload.get("strHomeTeam") or payload.get("strEvent") or "SportsDB Event")


def _normalize_sport(value: Any) -> str:
    sport = str(value or "sport").strip().lower()
    if sport == "soccer":
        return "soccer"
    if sport in {"american football", "football"}:
        return "american football"
    return sport


def _is_mock_identifier(value: str) -> bool:
    return not value.isdigit()


def _make_event(payload: Dict[str, Any]) -> Event:
    confidence = float(payload.get("confidence", 0.95))
    mock = bool(payload.get("mock", True))
    incomplete = bool(payload.get("incomplete", False))
    opponent = payload.get("opponent") or _opponent_from_title(
        payload["title"], payload["entity_name"]
    )
    display_time = payload.get("display_time") or _display_time(payload.get("start_time"))
    sport_icon = payload.get("sport_icon") or SPORT_ICONS.get(payload["sport"], "🏟️")
    entity = SportsEntity(
        name=payload["entity_name"],
        entity_type="team" if payload["event_type"] in {"game", "fixture", "match", "team_update"} else "athlete",
        sport=payload["sport"],
        league=payload["league"],
    )
    event = Event(
        title=payload["title"],
        event_type=payload["event_type"],
        start_time=payload["start_time"],
        sport_icon=sport_icon,
        opponent=opponent,
        display_time=display_time,
        confidence=confidence,
        mock=mock,
        incomplete=incomplete,
        entities=[entity],
        source_url=payload["source_url"],
        metadata={
            "sport": payload["sport"],
            "league": payload["league"],
            "confidence": confidence,
            "mock": mock,
            "incomplete": incomplete,
            "sport_icon": sport_icon,
            "opponent": opponent,
            "display_time": display_time,
        },
        entity_name=payload["entity_name"],
    )
    return event


def is_upcoming_event(event: Event, today: Optional[date] = None) -> bool:
    if not event.start_time:
        return True
    today = today or date.today()
    try:
        event_date = datetime.fromisoformat(event.start_time).date()
    except ValueError:
        try:
            event_date = date.fromisoformat(event.start_time[:10])
        except ValueError:
            return True
    return event_date >= today


def _display_time(start_time: Optional[str]) -> Optional[str]:
    if not start_time:
        return None
    try:
        parsed = datetime.fromisoformat(start_time)
    except ValueError:
        return start_time
    time_label = parsed.strftime("%I:%M %p").lstrip("0")
    offset = start_time[-6:] if len(start_time) >= 6 else ""
    zone_label = TIMEZONE_LABELS.get(offset, parsed.tzname() or "")
    suffix = f" {zone_label}" if zone_label else ""
    return f"{parsed.strftime('%a, %b')} {parsed.day}, {parsed.year} · {time_label}{suffix}"


def _opponent_from_title(title: str, entity_name: str) -> Optional[str]:
    marker = " vs "
    if marker not in title:
        return None
    left, right = title.split(marker, 1)
    if left.strip().lower() == entity_name.strip().lower():
        return right.strip()
    if right.strip().lower() == entity_name.strip().lower():
        return left.strip()
    return None


def _summarize_events(events: Iterable[Event]) -> str:
    titles = [event.title for event in events]
    if not titles:
        return "No upcoming mock events found."
    return " | ".join(titles)


def _event_key(record: Dict[str, Any]) -> str:
    return record.get("team_id") or _slug(record["canonical_name"])


def _slug(value: str) -> str:
    return value.strip().lower().replace(" ", "-")
