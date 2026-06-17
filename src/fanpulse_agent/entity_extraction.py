import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from fanpulse_agent.llm_reasoning import reason_about_user_message
from fanpulse_agent.models import SportsEntity, UserProfile


@dataclass(frozen=True)
class EntityDefinition:
    name: str
    entity_type: str
    sport: str
    aliases: Tuple[str, ...]
    league: Optional[str] = None
    confidence: float = 0.95
    needs_clarification: bool = False
    clarification_prompt: Optional[str] = None


ENTITY_CATALOG: Tuple[EntityDefinition, ...] = (
    EntityDefinition(
        name="Los Angeles Lakers",
        entity_type="team",
        sport="basketball",
        aliases=("Los Angeles Lakers", "Lakers"),
        league="NBA",
    ),
    EntityDefinition(
        name="Real Madrid",
        entity_type="team",
        sport="soccer",
        aliases=("Real Madrid",),
        league="La Liga",
    ),
    EntityDefinition(
        name="San Francisco 49ers",
        entity_type="team",
        sport="american football",
        aliases=("San Francisco 49ers", "49ers"),
        league="NFL",
    ),
    EntityDefinition(
        name="India Cricket",
        entity_type="team",
        sport="cricket",
        aliases=("India Cricket", "India cricket"),
        confidence=0.72,
        needs_clarification=True,
        clarification_prompt="Do you mean the India national cricket team?",
    ),
    EntityDefinition(
        name="Novak Djokovic",
        entity_type="athlete",
        sport="tennis",
        aliases=("Novak Djokovic", "Djokovic"),
    ),
    EntityDefinition(
        name="Max Verstappen",
        entity_type="athlete",
        sport="formula 1",
        aliases=("Max Verstappen", "Verstappen"),
    ),
    EntityDefinition(
        name="Formula 1",
        entity_type="league",
        sport="formula 1",
        aliases=("Formula 1", "F1"),
        league="Formula 1",
    ),
)


def extract_profile_from_text(text: str) -> tuple[UserProfile, list[SportsEntity]]:
    reasoned_facts = reason_about_user_message(text)
    entities = _extract_entities(text)
    entities = _merge_reasoned_entities(entities, reasoned_facts.teams, "team")
    entities = _merge_reasoned_entities(entities, reasoned_facts.athletes, "athlete")
    entities = _merge_reasoned_entities(entities, reasoned_facts.leagues, "league")
    teams = [entity for entity in entities if entity.entity_type == "team"]
    athletes = [entity for entity in entities if entity.entity_type == "athlete"]
    leagues = [entity for entity in entities if entity.entity_type == "league"]
    sports = _ordered_unique(
        [
            *(entity.sport for entity in entities if entity.sport),
            *reasoned_facts.sports,
        ]
    )
    name = reasoned_facts.name or _extract_name(text)
    phone_number = (
        _normalize_phone_number(reasoned_facts.phone_number)
        if reasoned_facts.phone_number
        else _extract_phone_number(text)
    )
    timezone = reasoned_facts.timezone or _extract_timezone(text)
    digest_schedule = _normalize_digest_schedule(
        reasoned_facts.digest_schedule or _extract_digest_schedule(text)
    )
    whatsapp_consent = (
        reasoned_facts.whatsapp_consent
        if reasoned_facts.whatsapp_consent is not None
        else _extract_whatsapp_consent(text)
    )

    profile = UserProfile(
        user_id="onboarding",
        name=name or "Fan",
        phone_number=phone_number,
        timezone=timezone or "America/Los_Angeles",
        digest_schedule=digest_schedule or "Friday morning",
        whatsapp_consent=whatsapp_consent,
        name_provided=bool(name),
        timezone_provided=bool(timezone),
        schedule_provided=bool(digest_schedule),
        teams=teams,
        athletes=athletes,
        leagues=leagues,
        sports=sports,
        favorite_teams=teams,
        favorite_sports=sports,
    )

    ambiguous = [
        entity
        for entity in entities
        if getattr(entity, "needs_clarification", False)
    ]
    return profile, ambiguous


def _extract_name(text: str) -> Optional[str]:
    patterns = (
        r"^\s*([A-Za-z][a-zA-Z'-]*)\s*,",
        r"\bI\s+am\s+(?!in\b|from\b|at\b)([A-Za-z][a-zA-Z'-]*)\b",
        r"\bI['’]m\s+(?!in\b|from\b|at\b)([A-Za-z][a-zA-Z'-]*)\b",
        r"\bmy\s+name(?:\s+is|['’]s)\s+([A-Za-z][a-zA-Z'-]*)\b",
        r"\bthis\s+is\s+([A-Za-z][a-zA-Z'-]*)\b",
        r"\bcall\s+me\s+([A-Za-z][a-zA-Z'-]*)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _normalize_name(match.group(1))

    bare_name = _extract_bare_name(text)
    return bare_name


def _extract_phone_number(text: str) -> Optional[str]:
    international = re.search(r"(?<!\w)(\+\d[\d\s().-]{7,}\d)(?!\w)", text)
    if international:
        return _normalize_phone_number(international.group(1))

    us_number = re.search(
        r"(?<!\w)(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\w)",
        text,
    )
    if us_number:
        digits = re.sub(r"\D", "", us_number.group(0))
        if len(digits) == 10:
            return f"+1{digits}"
    return None


def _normalize_phone_number(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return f"+{digits}" if digits else value


def _extract_timezone(text: str) -> Optional[str]:
    canonical_match = re.search(
        r"\b(?:timezone|time zone)\s+([A-Za-z_]+/[A-Za-z_]+)\b",
        text,
        re.IGNORECASE,
    )
    if canonical_match:
        return canonical_match.group(1)

    timezone_aliases = {
        "pacific": "America/Los_Angeles",
        "california": "America/Los_Angeles",
        "bay area": "America/Los_Angeles",
        "san francisco": "America/Los_Angeles",
        "sf": "America/Los_Angeles",
        "los angeles": "America/Los_Angeles",
        "pt": "America/Los_Angeles",
        "pst": "America/Los_Angeles",
        "pdt": "America/Los_Angeles",
        "eastern": "America/New_York",
        "new york": "America/New_York",
        "nyc": "America/New_York",
        "et": "America/New_York",
        "est": "America/New_York",
        "edt": "America/New_York",
        "central": "America/Chicago",
        "ct": "America/Chicago",
        "cst": "America/Chicago",
        "cdt": "America/Chicago",
        "mountain": "America/Denver",
        "mt": "America/Denver",
        "mst": "America/Denver",
        "mdt": "America/Denver",
        "india": "Asia/Kolkata",
        "ist": "Asia/Kolkata",
        "uae": "Asia/Dubai",
        "dubai": "Asia/Dubai",
        "london": "Europe/London",
        "uk": "Europe/London",
    }
    for alias, timezone in timezone_aliases.items():
        if re.search(
            rf"\b(?:in|from|use|timezone|time zone)?\s*{re.escape(alias)}\s*(?:time|timezone)?\b",
            text,
            re.IGNORECASE,
        ):
            return timezone
    return None


def _extract_bare_name(text: str) -> Optional[str]:
    cleaned = re.sub(r"[^\w\s'-]", " ", text).strip()
    words = cleaned.split()
    if not words or len(words) > 4:
        return None

    first = words[0]
    lower = first.lower()
    non_names = {
        "i",
        "my",
        "use",
        "timezone",
        "time",
        "pacific",
        "california",
        "eastern",
        "central",
        "mountain",
        "new",
        "san",
        "sf",
        "nyc",
        "india",
        "london",
        "dubai",
    }
    if lower in non_names or not re.match(r"^[A-Za-z][a-zA-Z'-]*$", first):
        return None
    if first[:1].isupper():
        return _normalize_name(first)
    return None


def _normalize_name(value: str) -> str:
    if not value:
        return value
    return value[:1].upper() + value[1:]


def _extract_digest_schedule(text: str) -> Optional[str]:
    hourly_match = re.search(
        r"\b(?:every\s+)?(?:1|one)\s*(?:hour|hr)\b|\bevery\s+hour\b|\bhourly\b",
        text,
        re.IGNORECASE,
    )
    if hourly_match:
        return "Every 1 hour"

    every_hours = re.search(
        r"\bevery\s+(\d+)\s*(?:hours|hrs)\b",
        text,
        re.IGNORECASE,
    )
    if every_hours:
        return f"Every {every_hours.group(1)} hours"

    if re.search(r"\b(?:daily|every\s+day)\b", text, re.IGNORECASE):
        return "Daily"

    match = re.search(
        r"\bdigest\s+every\s+([A-Za-z]+(?:\s+(?:morning|afternoon|evening|night))?)\b",
        text,
        re.IGNORECASE,
    )
    return _title_first_word(match.group(1)) if match else None


def _normalize_digest_schedule(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = value.strip()
    if re.search(r"\b(?:every\s+)?(?:1|one)\s*(?:hour|hr)\b|\bevery\s+hour\b|\bhourly\b", normalized, re.IGNORECASE):
        return "Every 1 hour"
    hours = re.search(r"\bevery\s+(\d+)\s*(?:hours|hrs)\b", normalized, re.IGNORECASE)
    if hours:
        count = hours.group(1)
        return f"Every {count} hour" if count == "1" else f"Every {count} hours"
    if re.search(r"\b(?:daily|every\s+day)\b", normalized, re.IGNORECASE):
        return "Daily"
    return _title_first_word(normalized)


def _extract_whatsapp_consent(text: str) -> bool:
    if not re.search(r"\bwhatsapp\b", text, re.IGNORECASE):
        return False

    refusal_patterns = (
        r"\bdo\s+not\s+send\b.*\bwhatsapp\b",
        r"\bdon't\s+send\b.*\bwhatsapp\b",
        r"\bno\s+whatsapp\b",
        r"\bdo\s+not\b.*\bwhatsapp\b",
    )
    return not any(re.search(pattern, text, re.IGNORECASE) for pattern in refusal_patterns)


def _extract_entities(text: str) -> List[SportsEntity]:
    entities: List[SportsEntity] = []
    seen_names = set()
    for definition in ENTITY_CATALOG:
        if definition.name in seen_names:
            continue
        matched_alias = _find_alias(text, definition.aliases)
        if matched_alias:
            entity = SportsEntity(
                name=definition.name,
                entity_type=definition.entity_type,
                sport=definition.sport,
                source_text=matched_alias,
                confidence=definition.confidence,
                needs_clarification=definition.needs_clarification,
                clarification_prompt=definition.clarification_prompt,
                league=definition.league,
            )
            entities.append(entity)
            seen_names.add(definition.name)
    return entities


def _merge_reasoned_entities(
    entities: List[SportsEntity],
    reasoned_entities: list[dict],
    entity_type: str,
) -> List[SportsEntity]:
    seen = {entity.name.strip().lower() for entity in entities}
    merged = list(entities)
    for item in reasoned_entities:
        name = str(item.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        sport = str(item.get("sport") or "soccer").strip().lower()
        league = item.get("league")
        merged.append(
            SportsEntity(
                name=name,
                entity_type=entity_type,
                sport=sport,
                source_text=name,
                confidence=0.72,
                league=str(league) if league else None,
            )
        )
        seen.add(name.lower())
    return merged


def _find_alias(text: str, aliases: Tuple[str, ...]) -> Optional[str]:
    for alias in aliases:
        match = re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def _ordered_unique(values):
    ordered = []
    seen = set()
    for value in values:
        if value not in seen:
            ordered.append(value)
            seen.add(value)
    return ordered


def _title_first_word(value: str) -> str:
    parts = value.split()
    if not parts:
        return value
    return " ".join([parts[0].capitalize(), *parts[1:]])
