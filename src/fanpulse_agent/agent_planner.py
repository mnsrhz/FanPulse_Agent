from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from fanpulse_agent.models import SportsEntity, UserProfile

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


ALLOWED_ACTIONS = (
    "collect_preferences",
    "collect_profile_details",
    "clarify_ambiguity",
    "confirm_preferences",
    "collect_contact",
    "approve_digest",
    "complete",
)

NEXT_ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "next_action": {
            "type": "string",
            "enum": list(ALLOWED_ACTIONS),
            "description": "The next safe agent action to take.",
        },
        "assistant_message": {
            "type": ["string", "null"],
            "description": "A concise user-facing message for the next action.",
        },
        "tool_plan": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Tool names the agent expects to call soon, if any.",
        },
        "reasoning": {
            "type": "string",
            "description": "Brief reasoning for the selected action.",
        },
    },
    "required": ["next_action", "assistant_message", "tool_plan", "reasoning"],
}

DIGEST_TOOL_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "tools": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Ordered known FanPulse tool names to call for digest creation.",
        },
        "reasoning": {
            "type": "string",
            "description": "Brief reason for the selected tool plan.",
        },
    },
    "required": ["tools", "reasoning"],
}


@dataclass(frozen=True)
class AgentPlan:
    next_action: str
    assistant_message: Optional[str] = None
    reasoning: str = ""
    tool_plan: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DigestToolPlan:
    tools: list[str] = field(default_factory=list)
    reasoning: str = ""


def plan_next_agent_action(
    *,
    user_message: str,
    profile: UserProfile,
    has_pending_digest: bool,
    ambiguous_entities: Sequence[SportsEntity],
    missing_fields: Sequence[str],
    contact_ready: bool,
) -> AgentPlan:
    allowed_actions = _allowed_next_actions(
        profile=profile,
        has_pending_digest=has_pending_digest,
        ambiguous_entities=ambiguous_entities,
        missing_fields=missing_fields,
        contact_ready=contact_ready,
    )
    fallback = _fallback_next_action(allowed_actions)
    if not _llm_enabled():
        return fallback

    plan = _call_next_action_llm(
        user_message=user_message,
        state={
            "allowed_actions": list(allowed_actions),
            "has_pending_digest": has_pending_digest,
            "ambiguous_entities": [entity.name for entity in ambiguous_entities],
            "missing_fields": list(missing_fields),
            "contact_ready": contact_ready,
            "profile": _profile_summary(profile),
        },
    )
    if plan.next_action not in allowed_actions:
        return fallback
    return plan


def plan_digest_tool_calls(profile: UserProfile) -> DigestToolPlan:
    fallback = _fallback_digest_tool_plan(profile)
    if not _llm_enabled():
        return fallback

    plan = _call_digest_tool_plan_llm(_profile_summary(profile))
    if not plan.tools:
        return fallback
    return plan


def _allowed_next_actions(
    *,
    profile: UserProfile,
    has_pending_digest: bool,
    ambiguous_entities: Sequence[SportsEntity],
    missing_fields: Sequence[str],
    contact_ready: bool,
) -> tuple[str, ...]:
    if has_pending_digest:
        return ("approve_digest",) if contact_ready else ("collect_contact",)
    if missing_fields:
        return ("collect_profile_details",)
    if not profile.teams and not profile.athletes and not profile.leagues and not profile.sports:
        return ("collect_preferences",)
    if ambiguous_entities:
        return ("clarify_ambiguity",)
    return ("confirm_preferences",)


def _fallback_next_action(allowed_actions: Sequence[str]) -> AgentPlan:
    next_action = allowed_actions[0] if allowed_actions else "collect_preferences"
    return AgentPlan(
        next_action=next_action,
        assistant_message=None,
        reasoning="Deterministic fallback selected the only currently safe action.",
        tool_plan=[],
    )


def _fallback_digest_tool_plan(profile: UserProfile) -> DigestToolPlan:
    tools: list[str] = []
    if profile.teams or profile.athletes or profile.leagues:
        tools.append("fanpulse.normalize_sports_entity")
        tools.extend(
            [
                "official-schedule.discover_sources",
                "official-schedule.extract_events",
                "official-schedule.validate_events",
            ]
        )
    if profile.teams:
        if any(team.sport == "soccer" for team in profile.teams):
            tools.append("api-football.search_soccer_fixture")
        if any(team.sport == "basketball" for team in profile.teams):
            tools.extend(["api-basketball.search_team", "api-basketball.get_team_games"])
        tools.extend(["thesportsdb.search_team", "thesportsdb.get_next_team_events"])
    if profile.athletes:
        if any(athlete.sport == "formula 1" for athlete in profile.athletes):
            tools.extend(
                [
                    "api-formula1.search_driver",
                    "api-formula1.get_next_races",
                    "api-formula1.get_driver_context",
                ]
            )
        tools.append("thesportsdb.search_player")
        tools.append("serpapi.search_sports_events")
    if profile.leagues:
        if any(league.sport == "soccer" for league in profile.leagues):
            tools.extend(
                [
                    "api-football.search_league",
                    "api-football.get_next_league_fixtures",
                ]
            )
        if any(league.sport == "basketball" for league in profile.leagues):
            tools.extend(["api-basketball.search_league", "api-basketball.get_league_games"])
        tools.extend(["thesportsdb.search_league", "thesportsdb.get_next_league_events"])
    if profile.sports:
        tools.append("serpapi.search_sports_news")
    tools.extend(["fanpulse.rank_events", "fanpulse.generate_digest"])
    return DigestToolPlan(
        tools=_ordered_unique(tools),
        reasoning="Deterministic fallback planned official schedule search first, then optional provider fallbacks.",
    )


def _profile_summary(profile: UserProfile) -> dict[str, Any]:
    return {
        "name": profile.name,
        "name_provided": profile.name_provided,
        "timezone": profile.timezone,
        "timezone_provided": profile.timezone_provided,
        "digest_schedule": profile.digest_schedule,
        "schedule_provided": profile.schedule_provided,
        "has_phone_number": bool(profile.phone_number),
        "whatsapp_consent": profile.whatsapp_consent,
        "teams": [team.to_dict() for team in profile.teams],
        "athletes": [athlete.to_dict() for athlete in profile.athletes],
        "leagues": [league.to_dict() for league in profile.leagues],
        "sports": list(profile.sports),
    }


def _llm_enabled() -> bool:
    return bool(
        os.environ.get("FANPULSE_DISABLE_LLM") != "1"
        and os.environ.get("OPENAI_API_KEY")
    )


def _call_next_action_llm(user_message: str, state: dict[str, Any]) -> AgentPlan:
    try:
        from openai import OpenAI

        client = OpenAI()
        response = client.responses.create(
            model=os.environ.get("FANPULSE_LLM_MODEL", "gpt-4o-mini"),
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are the planning brain for FanPulse, a sports digest agent. "
                        "Choose the best next action from allowed_actions only. Ask for "
                        "missing preferences, name, timezone, or contact details naturally. "
                        "Never choose sending actions unless the state says they are allowed."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"user_message": user_message, "state": state},
                        sort_keys=True,
                    ),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "fanpulse_next_action",
                    "strict": True,
                    "schema": NEXT_ACTION_SCHEMA,
                }
            },
        )
        payload = json.loads(response.output_text)
    except Exception:
        return AgentPlan(next_action="collect_preferences")

    return AgentPlan(
        next_action=str(payload.get("next_action") or "collect_preferences"),
        assistant_message=_string_or_none(payload.get("assistant_message")),
        reasoning=str(payload.get("reasoning") or ""),
        tool_plan=[
            str(tool)
            for tool in payload.get("tool_plan", [])
            if isinstance(tool, str) and tool
        ],
    )


def _call_digest_tool_plan_llm(profile_summary: dict[str, Any]) -> DigestToolPlan:
    try:
        from openai import OpenAI

        client = OpenAI()
        response = client.responses.create(
            model=os.environ.get("FANPULSE_LLM_MODEL", "gpt-4o-mini"),
            input=[
                {
                    "role": "system",
                    "content": (
                        "Plan the ordered FanPulse tool calls needed to create a sports "
                        "digest. Use only known tools: fanpulse.normalize_sports_entity, "
                        "official-schedule.discover_sources, "
                        "official-schedule.extract_events, "
                        "official-schedule.validate_events, "
                        "api-football.search_soccer_fixture, api-football.search_league, "
                        "api-football.get_next_league_fixtures, thesportsdb.search_team, "
                        "thesportsdb.get_next_team_events, api-basketball.search_team, "
                        "api-basketball.get_team_games, api-basketball.search_league, "
                        "api-basketball.get_league_games, api-formula1.search_driver, "
                        "api-formula1.get_next_races, api-formula1.get_driver_context, "
                        "thesportsdb.search_player, thesportsdb.search_league, "
                        "thesportsdb.get_next_league_events, serpapi.search_sports_events, "
                        "serpapi.search_sports_news, web.search_event_source, "
                        "fanpulse.rank_events, fanpulse.generate_digest. Prefer official "
                        "schedule discovery, extraction, and validation before sports APIs. "
                        "Use api-football, api-basketball, api-formula1, SportsDB, SerpAPI, "
                        "and web tools as optional fallback providers."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(profile_summary, sort_keys=True),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "fanpulse_digest_tool_plan",
                    "strict": True,
                    "schema": DIGEST_TOOL_PLAN_SCHEMA,
                }
            },
        )
        payload = json.loads(response.output_text)
    except Exception:
        return DigestToolPlan()

    return DigestToolPlan(
        tools=[
            str(tool)
            for tool in payload.get("tools", [])
            if isinstance(tool, str) and tool
        ],
        reasoning=str(payload.get("reasoning") or ""),
    )


def _ordered_unique(values: Sequence[str]) -> list[str]:
    ordered: list[str] = []
    seen = set()
    for value in values:
        if value not in seen:
            ordered.append(value)
            seen.add(value)
    return ordered


def _string_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
