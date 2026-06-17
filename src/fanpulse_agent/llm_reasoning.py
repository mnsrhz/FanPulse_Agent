from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


@dataclass(frozen=True)
class ReasonedUserFacts:
    name: Optional[str] = None
    timezone: Optional[str] = None
    phone_number: Optional[str] = None
    whatsapp_consent: Optional[bool] = None
    digest_schedule: Optional[str] = None
    teams: list[dict[str, Any]] = field(default_factory=list)
    athletes: list[dict[str, Any]] = field(default_factory=list)
    leagues: list[dict[str, Any]] = field(default_factory=list)
    sports: list[str] = field(default_factory=list)
    reasoning: str = ""


USER_FACTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {
            "type": ["string", "null"],
            "description": "The user's first name when the message provides it, including bare replies like 'Mansoor'.",
        },
        "timezone": {
            "type": ["string", "null"],
            "description": "IANA timezone inferred from explicit timezone or location, such as America/Los_Angeles.",
        },
        "phone_number": {
            "type": ["string", "null"],
            "description": "A phone number if present. Preserve enough digits to normalize later.",
        },
        "whatsapp_consent": {
            "type": ["boolean", "null"],
            "description": "True if the user wants WhatsApp delivery, false if they refuse it, null if not mentioned.",
        },
        "digest_schedule": {
            "type": ["string", "null"],
            "description": "The requested recurring digest cadence, such as Friday morning, daily, hourly, or every 1 hour.",
        },
        "teams": {
            "type": "array",
            "description": "Sports teams, clubs, or national teams the user wants to follow.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "sport": {
                        "type": ["string", "null"],
                        "description": "Likely sport, such as soccer, basketball, cricket, american football.",
                    },
                    "league": {
                        "type": ["string", "null"],
                        "description": "Likely league or competition, if implied.",
                    },
                },
                "required": ["name", "sport", "league"],
            },
        },
        "athletes": {
            "type": "array",
            "description": "Individual athletes or drivers the user wants to follow.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "sport": {"type": ["string", "null"]},
                    "league": {"type": ["string", "null"]},
                },
                "required": ["name", "sport", "league"],
            },
        },
        "leagues": {
            "type": "array",
            "description": "Leagues or competitions the user wants to follow.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "sport": {"type": ["string", "null"]},
                    "league": {"type": ["string", "null"]},
                },
                "required": ["name", "sport", "league"],
            },
        },
        "sports": {
            "type": "array",
            "description": "Sports explicitly or implicitly represented by the user's preferences.",
            "items": {"type": "string"},
        },
        "reasoning": {
            "type": "string",
            "description": "Brief explanation of what was inferred and why.",
        },
    },
    "required": [
        "name",
        "timezone",
        "phone_number",
        "whatsapp_consent",
        "digest_schedule",
        "teams",
        "athletes",
        "leagues",
        "sports",
        "reasoning",
    ],
}


@lru_cache(maxsize=128)
def reason_about_user_message(text: str) -> ReasonedUserFacts:
    if os.environ.get("FANPULSE_DISABLE_LLM") == "1" or not os.environ.get("OPENAI_API_KEY"):
        return ReasonedUserFacts()

    try:
        from openai import OpenAI

        client = OpenAI()
        response = client.responses.create(
            model=os.environ.get("FANPULSE_LLM_MODEL", "gpt-4o-mini"),
            input=[
                {
                    "role": "system",
                    "content": (
                        "You extract onboarding facts for FanPulse, a sports digest agent. "
                        "Reason over short, contextual replies. If the assistant just asked for a "
                        "name and timezone, a reply like 'Mansoor, California' means name=Mansoor "
                        "and timezone=America/Los_Angeles. Infer common locations into IANA "
                        "timezones. Extract requested update cadence/frequency, including "
                        "phrases like hourly or every 1 hour. Extract all teams, clubs, national teams, athletes, and "
                        "sports preferences mentioned, even when they are outside the local mock "
                        "catalog. Do not invent fields that are not implied."
                    ),
                },
                {"role": "user", "content": text},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "fanpulse_user_facts",
                    "strict": True,
                    "schema": USER_FACTS_SCHEMA,
                }
            },
        )
        payload = json.loads(response.output_text)
    except Exception:
        return ReasonedUserFacts()

    if not isinstance(payload, dict):
        return ReasonedUserFacts()
    return ReasonedUserFacts(
        name=_string_or_none(payload.get("name")),
        timezone=_string_or_none(payload.get("timezone")),
        phone_number=_string_or_none(payload.get("phone_number")),
        whatsapp_consent=payload.get("whatsapp_consent")
        if isinstance(payload.get("whatsapp_consent"), bool)
        else None,
        digest_schedule=_string_or_none(payload.get("digest_schedule")),
        teams=_entity_list(payload.get("teams")),
        athletes=_entity_list(payload.get("athletes")),
        leagues=_entity_list(payload.get("leagues")),
        sports=[
            sport
            for sport in (_string_or_none(value) for value in payload.get("sports", []))
            if sport
        ],
        reasoning=str(payload.get("reasoning") or ""),
    )


def _string_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _entity_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entities: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = _string_or_none(item.get("name"))
        if not name:
            continue
        entities.append(
            {
                "name": name,
                "sport": _string_or_none(item.get("sport")),
                "league": _string_or_none(item.get("league")),
            }
        )
    return entities
