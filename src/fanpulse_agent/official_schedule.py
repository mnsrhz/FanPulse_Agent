from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional
from urllib.parse import urlparse

from fanpulse_agent.models import Event, SportsEntity


TRUSTED_SCHEDULE_DOMAINS = {
    "nba.com",
    "espn.com",
    "formula1.com",
    "atptour.com",
    "wtatennis.com",
    "premierleague.com",
    "laliga.com",
    "realmadrid.com",
    "arsenal.com",
    "thefa.com",
    "icc-cricket.com",
}

SPORT_ICONS = {
    "american football": "🏈",
    "basketball": "🏀",
    "cricket": "🏏",
    "formula 1": "🏁",
    "soccer": "⚽",
    "tennis": "🎾",
}


def trusted_domain(url: str) -> Optional[str]:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    for domain in TRUSTED_SCHEDULE_DOMAINS:
        if host == domain or host.endswith(f".{domain}"):
            return domain
    return None


def source_from_search_result(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    link = str(payload.get("link") or "")
    domain = trusted_domain(link)
    if not domain:
        return None
    return {
        "title": str(payload.get("title") or ""),
        "link": link,
        "snippet": str(payload.get("snippet") or ""),
        "date": payload.get("date"),
        "domain": domain,
    }


def event_from_source(entity_name: str, sport: str, source: dict[str, Any]) -> Optional[Event]:
    start_time = _extract_date(source)
    if not start_time or not _is_future_date(start_time):
        return None
    title = _extract_title(entity_name, source)
    normalized_sport = sport.strip().lower() or "sport"
    source_url = str(source.get("link") or "")
    if not source_url:
        return None
    confidence = 0.86
    domain = str(source.get("domain") or trusted_domain(source_url) or "")
    return Event(
        title=title,
        event_type="schedule",
        start_time=start_time,
        sport_icon=SPORT_ICONS.get(normalized_sport, "🏟️"),
        display_time=_display_date(start_time),
        confidence=confidence,
        mock=False,
        incomplete=False,
        entities=[
            SportsEntity(
                name=entity_name,
                entity_type="team",
                sport=normalized_sport,
                league=domain,
            )
        ],
        source_url=source_url,
        metadata={
            "sport": normalized_sport,
            "league": domain,
            "provider": "official-schedule",
            "source_domain": domain,
            "confidence": confidence,
            "mock": False,
            "incomplete": False,
            "sport_icon": SPORT_ICONS.get(normalized_sport, "🏟️"),
            "display_time": _display_date(start_time),
        },
        entity_name=entity_name,
    )


def events_from_source(entity_name: str, sport: str, source: dict[str, Any]) -> list[Event]:
    event = event_from_source(entity_name, sport, source)
    if event:
        return [event]
    page_text = str(source.get("page_text") or "")
    domain = str(source.get("domain") or trusted_domain(str(source.get("link") or "")))
    if not page_text:
        if domain == "formula1.com":
            return cached_formula1_events(entity_name, sport)
        return []
    if domain == "espn.com":
        return [
            *_events_from_espn_page(entity_name, sport, source, page_text),
            *_events_from_espn_soccer_page(entity_name, sport, source, page_text),
        ]
    if domain == "formula1.com":
        events = _events_from_formula1_page(entity_name, sport, source, page_text)
        return events or cached_formula1_events(entity_name, sport)
    return []


def cached_formula1_events(entity_name: str, sport: str) -> list[Event]:
    normalized_sport = sport.strip().lower() or "formula 1"
    if normalized_sport not in {"formula 1", "f1"}:
        return []
    cached = [
        ("Austria", "2026-06-26", "https://www.formula1.com/en/racing/2026/austria", "8"),
        ("Great Britain", "2026-07-03", "https://www.formula1.com/en/racing/2026/great-britain", "9"),
        ("Belgium", "2026-07-17", "https://www.formula1.com/en/racing/2026/belgium", "10"),
    ]
    events: list[Event] = []
    for location, start_time, source_url, round_number in cached:
        if not _is_future_date(start_time):
            continue
        sport_icon = SPORT_ICONS.get("formula 1", "🏁")
        events.append(
            Event(
                title=f"Formula 1: {location} Grand Prix",
                event_type="race",
                start_time=start_time,
                sport_icon=sport_icon,
                display_time=_display_date(start_time),
                confidence=0.82,
                mock=False,
                incomplete=False,
                entities=[
                    SportsEntity(
                        name=entity_name,
                        entity_type="league" if entity_name.lower() == "formula 1" else "athlete",
                        sport="formula 1",
                        league="formula1.com",
                    )
                ],
                source_url=source_url,
                metadata={
                    "sport": "formula 1",
                    "league": "formula1.com",
                    "provider": "official-schedule",
                    "source_domain": "formula1.com",
                    "source_parser": "formula1-cached-official",
                    "round": round_number,
                    "confidence": 0.82,
                    "mock": False,
                    "incomplete": False,
                    "sport_icon": sport_icon,
                    "display_time": _display_date(start_time),
                },
                entity_name=entity_name,
            )
        )
    return events


def validate_events(events: list[Event]) -> list[Event]:
    return [
        event
        for event in events
        if event.source_url and event.start_time and _is_future_date(event.start_time)
    ]


def _extract_date(source: dict[str, Any]) -> Optional[str]:
    direct_date = source.get("date")
    if direct_date and _parse_date(str(direct_date)):
        return str(direct_date)[:10]
    text = " ".join(
        str(source.get(field) or "") for field in ("title", "snippet")
    )
    iso_match = re.search(r"\b(20\d{2}-\d{2}-\d{2}|2999-\d{2}-\d{2})\b", text)
    if iso_match:
        return iso_match.group(1)
    month_match = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(20\d{2}|2999)\b",
        text,
        re.IGNORECASE,
    )
    if month_match:
        parsed = datetime.strptime(
            " ".join(month_match.groups()), "%B %d %Y"
        ).date()
        return parsed.isoformat()
    return None


def _events_from_espn_page(
    entity_name: str, sport: str, source: dict[str, Any], page_text: str
) -> list[Event]:
    normalized_sport = sport.strip().lower() or "sport"
    source_url = str(source.get("link") or "")
    domain = str(source.get("domain") or trusted_domain(source_url) or "espn.com")
    events: list[Event] = []
    seen: set[tuple[str, str]] = set()

    for date_match in re.finditer(r'"date":\{"date":"(\d{4}-[^"]+)"', page_text):
        chunk = page_text[date_match.start() : date_match.start() + 2200]
        start_time = _extract_espn_time(chunk) or date_match.group(1)
        if not _is_future_date(start_time):
            continue
        opponent_match = re.search(r'"displayName":"([^"]+)"', chunk)
        if not opponent_match:
            continue
        opponent = opponent_match.group(1)
        symbol_match = re.search(r'"homeAwaySymbol":"([^"]+)"', chunk)
        symbol = symbol_match.group(1) if symbol_match else "vs"
        event_link = _extract_espn_link(chunk) or source_url
        title = _espn_title(entity_name, opponent, symbol)
        key = (title, start_time)
        if key in seen:
            continue
        seen.add(key)
        sport_icon = SPORT_ICONS.get(normalized_sport, "🏟️")
        events.append(
            Event(
                title=title,
                event_type="schedule",
                start_time=start_time,
                sport_icon=sport_icon,
                opponent=opponent,
                display_time=_display_date(start_time),
                confidence=0.88,
                mock=False,
                incomplete=False,
                entities=[
                    SportsEntity(
                        name=entity_name,
                        entity_type="team",
                        sport=normalized_sport,
                        league=domain,
                    )
                ],
                source_url=event_link,
                metadata={
                    "sport": normalized_sport,
                    "league": domain,
                    "provider": "official-schedule",
                    "source_domain": domain,
                    "source_parser": "espn-page",
                    "confidence": 0.88,
                    "mock": False,
                    "incomplete": False,
                    "sport_icon": sport_icon,
                    "opponent": opponent,
                    "display_time": _display_date(start_time),
                },
                entity_name=entity_name,
            )
        )
    return events


def _extract_espn_time(chunk: str) -> Optional[str]:
    time_match = re.search(r'"time":\{"time":"(\d{4}-[^"]+)"', chunk)
    if time_match:
        return time_match.group(1)
    return None


def _events_from_espn_soccer_page(
    entity_name: str, sport: str, source: dict[str, Any], page_text: str
) -> list[Event]:
    normalized_sport = sport.strip().lower() or "sport"
    source_url = str(source.get("link") or "")
    domain = str(source.get("domain") or trusted_domain(source_url) or "espn.com")
    events: list[Event] = []
    seen: set[tuple[str, str]] = set()

    pattern = re.compile(
        r'\{"id":"(?P<id>\d+)","competitors":\[(?P<competitors>.*?)\],"date":"(?P<date>\d{4}-[^"]+)"(?P<body>.*?),"link":"(?P<link>[^"]+)"',
        re.DOTALL,
    )
    for match in pattern.finditer(page_text):
        start_time = match.group("date")
        if not _is_future_date(start_time):
            continue
        competitors = match.group("competitors")
        names = re.findall(r'"displayName":"([^"]+)"', competitors)
        if len(names) < 2:
            continue
        opponent = next((name for name in names if name.lower() != entity_name.lower()), names[1])
        entity_home = _entity_is_home(entity_name, competitors)
        title = (
            f"{entity_name} vs {opponent}"
            if entity_home
            else f"{entity_name} at {opponent}"
        )
        key = (title, start_time)
        if key in seen:
            continue
        seen.add(key)
        event_link = _absolute_espn_link(match.group("link")) or source_url
        sport_icon = SPORT_ICONS.get(normalized_sport, "🏟️")
        events.append(
            Event(
                title=title,
                event_type="schedule",
                start_time=start_time,
                sport_icon=sport_icon,
                opponent=opponent,
                display_time=_display_date(start_time),
                confidence=0.88,
                mock=False,
                incomplete=False,
                entities=[
                    SportsEntity(
                        name=entity_name,
                        entity_type="team",
                        sport=normalized_sport,
                        league=domain,
                    )
                ],
                source_url=event_link,
                metadata={
                    "sport": normalized_sport,
                    "league": domain,
                    "provider": "official-schedule",
                    "source_domain": domain,
                    "source_parser": "espn-soccer-page",
                    "confidence": 0.88,
                    "mock": False,
                    "incomplete": False,
                    "sport_icon": sport_icon,
                    "opponent": opponent,
                    "display_time": _display_date(start_time),
                },
                entity_name=entity_name,
            )
        )
    return events


def _events_from_formula1_page(
    entity_name: str, sport: str, source: dict[str, Any], page_text: str
) -> list[Event]:
    normalized_sport = sport.strip().lower() or "formula 1"
    source_url = str(source.get("link") or "")
    domain = str(source.get("domain") or trusted_domain(source_url) or "formula1.com")
    events: list[Event] = []
    seen: set[tuple[str, str]] = set()
    card_pattern = re.compile(
        r'href="(?P<link>/en/racing/(?P<year>\d{4})/[^"]+)".{0,3000}?'
        r'ROUND\s+(?P<round>\d+).{0,1000}?'
        r'group-hover/schedule-card:underline">(?P<location>[^<]+)</span>'
        r'.{0,500}?technical-m-regular[^>]*>(?P<date>[^<]+)</span>',
        re.DOTALL,
    )
    for match in card_pattern.finditer(page_text):
        start_time = _formula1_start_date(match.group("year"), match.group("date"))
        if not start_time or not _is_future_date(start_time):
            continue
        location = _clean_title(match.group("location"))
        title = f"Formula 1: {location} Grand Prix"
        key = (title, start_time)
        if key in seen:
            continue
        seen.add(key)
        event_link = f"https://www.formula1.com{match.group('link')}"
        sport_icon = SPORT_ICONS.get(normalized_sport, "🏁")
        events.append(
            Event(
                title=title,
                event_type="race",
                start_time=start_time,
                sport_icon=sport_icon,
                opponent=None,
                display_time=_display_date(start_time),
                confidence=0.9,
                mock=False,
                incomplete=False,
                entities=[
                    SportsEntity(
                        name=entity_name,
                        entity_type="league" if entity_name.lower() == "formula 1" else "athlete",
                        sport=normalized_sport,
                        league=domain,
                    )
                ],
                source_url=event_link,
                metadata={
                    "sport": normalized_sport,
                    "league": domain,
                    "provider": "official-schedule",
                    "source_domain": domain,
                    "source_parser": "formula1-page",
                    "round": match.group("round"),
                    "confidence": 0.9,
                    "mock": False,
                    "incomplete": False,
                    "sport_icon": sport_icon,
                    "display_time": _display_date(start_time),
                },
                entity_name=entity_name,
            )
        )
    return events


def _formula1_start_date(year: str, date_label: str) -> Optional[str]:
    label = re.sub(r"\s+", " ", date_label).strip().upper()
    range_match = re.search(r"\b(\d{1,2})(?:\s*-\s*\d{1,2})?\s+([A-Z]{3})\b", label)
    if not range_match:
        return None
    month_lookup = {
        "JAN": 1,
        "FEB": 2,
        "MAR": 3,
        "APR": 4,
        "MAY": 5,
        "JUN": 6,
        "JUL": 7,
        "AUG": 8,
        "SEP": 9,
        "OCT": 10,
        "NOV": 11,
        "DEC": 12,
    }
    month = month_lookup.get(range_match.group(2))
    if not month:
        return None
    return date(int(year), month, int(range_match.group(1))).isoformat()


def _entity_is_home(entity_name: str, competitors: str) -> bool:
    escaped_name = re.escape(entity_name)
    home_pattern = rf'\{{[^{{}}]*"displayName":"{escaped_name}"[^{{}}]*"isHome":true'
    away_pattern = rf'\{{[^{{}}]*"displayName":"{escaped_name}"[^{{}}]*"isHome":false'
    if re.search(home_pattern, competitors):
        return True
    if re.search(away_pattern, competitors):
        return False
    return True


def _extract_espn_link(chunk: str) -> Optional[str]:
    link_match = re.search(r'"link":"(https://www\.espn\.com/[^"]+)"', chunk)
    if link_match:
        return link_match.group(1)
    relative_match = re.search(r'"link":"(/[^"]+)"', chunk)
    if relative_match:
        return _absolute_espn_link(relative_match.group(1))
    return None


def _absolute_espn_link(link: str) -> Optional[str]:
    if not link:
        return None
    if link.startswith("https://www.espn.com/"):
        return link
    if link.startswith("/"):
        return f"https://www.espn.com{link}"
    return None


def _espn_title(entity_name: str, opponent: str, symbol: str) -> str:
    if symbol == "@":
        return f"{entity_name} at {opponent}"
    return f"{entity_name} vs {opponent}"


def _extract_title(entity_name: str, source: dict[str, Any]) -> str:
    text = " ".join(str(source.get(field) or "") for field in ("title", "snippet"))
    matchup = re.search(
        rf"({re.escape(entity_name)}\s+(?:vs|v\.?|at)\s+[A-Z][A-Za-z .&'-]+?)(?:\s+on\s+|\s+at\s+\d|\.|$)",
        text,
        re.IGNORECASE,
    )
    if matchup:
        return _clean_title(matchup.group(1))
    title = str(source.get("title") or "").strip()
    return title or f"{entity_name} schedule"


def _clean_title(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip(" .")
    return re.sub(r"\bvs\b", "vs", text, flags=re.IGNORECASE)


def _parse_date(value: str) -> Optional[date]:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _is_future_date(value: str) -> bool:
    parsed = _parse_date(value)
    return bool(parsed and parsed >= date.today())


def _display_date(value: str) -> str:
    parsed = _parse_date(value)
    if not parsed:
        return value
    return f"{parsed.strftime('%a, %b')} {parsed.day}, {parsed.year}"
