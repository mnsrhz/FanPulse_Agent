import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

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
)


def extract_profile_from_text(text: str) -> tuple[UserProfile, list[SportsEntity]]:
    entities = _extract_entities(text)
    teams = [entity for entity in entities if entity.entity_type == "team"]
    athletes = [entity for entity in entities if entity.entity_type == "athlete"]
    sports = _ordered_unique(entity.sport for entity in entities if entity.sport)

    profile = UserProfile(
        user_id="onboarding",
        name=_extract_name(text) or "Fan",
        phone_number=_extract_phone_number(text),
        timezone=_extract_timezone(text) or "America/Los_Angeles",
        digest_schedule=_extract_digest_schedule(text) or "Friday morning",
        whatsapp_consent=bool(re.search(r"\bwhatsapp\b", text, re.IGNORECASE)),
        teams=teams,
        athletes=athletes,
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
    match = re.search(r"\bI\s+am\s+([A-Z][a-zA-Z'-]*)\b", text)
    return match.group(1) if match else None


def _extract_phone_number(text: str) -> Optional[str]:
    match = re.search(r"(?<!\w)(\+\d{8,15})(?!\w)", text)
    return match.group(1) if match else None


def _extract_timezone(text: str) -> Optional[str]:
    match = re.search(r"\b(?:timezone|time zone)\s+([A-Za-z_/+-]+)\b", text, re.IGNORECASE)
    return match.group(1) if match else None


def _extract_digest_schedule(text: str) -> Optional[str]:
    match = re.search(
        r"\bdigest\s+every\s+([A-Za-z]+(?:\s+(?:morning|afternoon|evening|night))?)\b",
        text,
        re.IGNORECASE,
    )
    return _title_first_word(match.group(1)) if match else None


def _extract_entities(text: str) -> List[SportsEntity]:
    entities: List[SportsEntity] = []
    seen_names = set()
    for definition in ENTITY_CATALOG:
        if definition.name in seen_names:
            continue
        if any(_contains_alias(text, alias) for alias in definition.aliases):
            entity = SportsEntity(
                name=definition.name,
                entity_type=definition.entity_type,
                sport=definition.sport,
                source_text=definition.name,
                confidence=definition.confidence,
                needs_clarification=definition.needs_clarification,
                clarification_prompt=definition.clarification_prompt,
                league=definition.league,
            )
            entities.append(entity)
            seen_names.add(definition.name)
    return entities


def _contains_alias(text: str, alias: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text, re.IGNORECASE) is not None


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
