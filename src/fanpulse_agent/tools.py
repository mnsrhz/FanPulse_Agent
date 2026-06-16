from typing import Any, Callable, Dict, Iterable, List, Optional

from fanpulse_agent.models import Digest, Event, SportsEntity, ToolResult, UserProfile


SPORTSDB_SOURCE_URL = "https://www.thesportsdb.com/"
API_FOOTBALL_SOURCE_URL = "https://www.api-football.com/"
WEB_SEARCH_SOURCE_URL = "https://search.example.com/fanpulse-mock"
WHATSAPP_SOURCE_URL = "https://business.whatsapp.com/"
FANPULSE_SOURCE_URL = "mock://fanpulse-agent"


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
    events = [_make_event(payload) for payload in MOCK_EVENTS.get(team_id, [])]
    return _result(
        "thesportsdb.get_next_team_events",
        bool(events),
        {"team_id": team_id, "events": events},
        SPORTSDB_SOURCE_URL,
        error=None if events else f"No mock events found for team_id {team_id}",
        confidence=0.95 if events else 0.25,
    )


def search_soccer_fixture_apifootball(entity_name: str) -> ToolResult:
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


def web_search_event_source(entity_name: str) -> ToolResult:
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
    "api-football.search_soccer_fixture": search_soccer_fixture_apifootball,
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
) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        success=success,
        data=data,
        source_url=source_url,
        error=error,
        confidence=confidence,
        mock=True,
    )


def _lookup_entity(entity_name: str) -> Optional[Dict[str, Any]]:
    query = entity_name.strip().lower()
    for record in ENTITY_CATALOG.values():
        if query in record["aliases"]:
            return record
    return ENTITY_CATALOG.get(query)


def _make_event(payload: Dict[str, Any]) -> Event:
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
        entities=[entity],
        source_url=payload["source_url"],
        metadata={"sport": payload["sport"], "league": payload["league"]},
        entity_name=payload["entity_name"],
    )
    return event


def _summarize_events(events: Iterable[Event]) -> str:
    titles = [event.title for event in events]
    if not titles:
        return "No upcoming mock events found."
    return " | ".join(titles)


def _event_key(record: Dict[str, Any]) -> str:
    return record.get("team_id") or _slug(record["canonical_name"])


def _slug(value: str) -> str:
    return value.strip().lower().replace(" ", "-")
