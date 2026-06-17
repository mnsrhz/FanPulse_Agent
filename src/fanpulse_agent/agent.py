from dataclasses import dataclass, field
from typing import List, Optional

from fanpulse_agent.database import FanPulseDB
from fanpulse_agent.entity_extraction import extract_profile_from_text
from fanpulse_agent.models import Digest, Event, SportsEntity, ToolResult, TraceEntry, UserProfile
from fanpulse_agent.tools import (
    generate_digest,
    get_next_team_events_thesportsdb,
    normalize_sports_entity,
    rank_events,
    search_soccer_fixture_apifootball,
    search_team_thesportsdb,
    send_whatsapp_digest,
    web_search_event_source,
)


@dataclass
class AgentResponse:
    message: str
    requires_action: str
    profile: Optional[UserProfile] = None
    digest: Optional[Digest] = None
    trace: List[TraceEntry] = field(default_factory=list)


class FanPulseAgent:
    def __init__(self, db: FanPulseDB):
        self.db = db
        self.db.initialize()
        self.current_profile: Optional[UserProfile] = None
        self.current_digest: Optional[Digest] = None
        self.current_user_id: Optional[int] = None
        self.trace: List[TraceEntry] = []
        self._ambiguous_entities: List[SportsEntity] = []

    def handle_user_message(self, text: str) -> AgentResponse:
        profile, ambiguous = extract_profile_from_text(text)
        self.current_profile = profile
        self.current_digest = None
        self.current_user_id = None
        self._ambiguous_entities = ambiguous
        self.trace = []
        self._trace(
            "plan_onboarding",
            "Extracted fan preferences and planned approval-gated onboarding.",
            metadata={
                "team_count": len(profile.teams),
                "athlete_count": len(profile.athletes),
                "ambiguous_count": len(ambiguous),
            },
        )

        if ambiguous:
            names = ", ".join(entity.name for entity in ambiguous)
            return self._response(
                f"Please clarify this preference before I continue: {names}.",
                "clarify_ambiguity",
            )
        return self._confirm_preferences_response()

    def resolve_ambiguity(self, choice: str) -> AgentResponse:
        profile = self._require_profile()
        for entity in self._ambiguous_entities:
            profile.clarification_choices[entity.name] = choice
            entity.needs_clarification = False
        self._ambiguous_entities = []
        self._trace(
            "resolve_ambiguity",
            "Stored clarification choice.",
            metadata={"choice": choice},
        )
        return self._confirm_preferences_response()

    def confirm_preferences(self) -> AgentResponse:
        profile = self._require_profile()
        if profile.user_id == "onboarding":
            profile.user_id = None
        user_id = self.db.save_user_preferences(profile)
        profile.user_id = str(user_id)
        self.current_user_id = user_id
        self._log_tool(
            ToolResult(
                "sqlite.save_state",
                True,
                {"user_id": user_id, "profile_name": profile.name},
                None,
                None,
                1.0,
            )
        )
        self._trace(
            "persist_state",
            "Saved onboarding state.",
            tool_name="sqlite.save_state",
            metadata={"user_id": user_id},
            persist=True,
        )

        events, unresolved = self._collect_events(profile)
        ranked = self._log_tool(rank_events(events, profile))
        ranked_events = ranked.data["events"] if ranked.success else events
        digest_result = self._log_tool(generate_digest(ranked_events, profile))
        digest = digest_result.data["digest"]
        digest.approved = False
        digest.sent = False
        digest.unresolved = unresolved
        self.current_digest = digest
        self._trace(
            "await_digest_approval",
            "Generated digest and paused before sending.",
            tool_name=digest_result.tool_name,
            metadata={"event_count": len(digest.events), "unresolved": unresolved},
            persist=True,
        )
        return self._response("Please approve this digest before I send it.", "approve_digest")

    def approve_and_send_digest(self) -> AgentResponse:
        profile = self._require_profile()
        digest = self._require_digest()
        if getattr(digest, "sent", False):
            digest.approved = True
            return self._response("Digest already sent.", "complete")

        if not profile.whatsapp_consent or not profile.phone_number:
            self._trace(
                "send_blocked",
                "WhatsApp send blocked because consent or phone number is missing.",
                metadata={
                    "has_consent": profile.whatsapp_consent,
                    "has_phone": bool(profile.phone_number),
                },
                persist=bool(self.current_user_id),
            )
            return self._response(
                "I need WhatsApp consent and a phone number before sending.",
                "confirm_preferences",
            )

        result = self._log_tool(
            send_whatsapp_digest(profile.phone_number, self._digest_text(digest))
        )
        if result.success:
            digest.approved = True
            digest.sent = True
            user_id = self._ensure_user_id(profile)
            self.db.save_digest_history(user_id, digest)
            self._log_tool(
                ToolResult(
                    "sqlite.save_digest_history",
                    True,
                    {"user_id": user_id, "digest_title": digest.title},
                    None,
                    None,
                    1.0,
                )
            )
            self._trace(
                "complete",
                "Approved digest was sent and saved.",
                tool_name=result.tool_name,
                metadata={"user_id": user_id},
                persist=True,
            )
            return self._response("Digest sent.", "complete")

        digest.approved = True
        digest.sent = False
        self._trace(
            "send_failed",
            "WhatsApp send failed.",
            tool_name=result.tool_name,
            metadata={"error": result.error},
            persist=bool(self.current_user_id),
        )
        return self._response("Digest approval recorded, but sending failed.", "approve_digest")

    def run_weekly_digest_for_profile(self, profile: UserProfile) -> Digest:
        self.current_profile = profile
        self.current_user_id = self._ensure_user_id(profile)
        self.current_digest = None
        self.trace = []
        events, unresolved = self._collect_events(profile)
        ranked = self._log_tool(rank_events(events, profile))
        ranked_events = ranked.data["events"] if ranked.success else events
        digest_result = self._log_tool(generate_digest(ranked_events, profile))
        digest = digest_result.data["digest"]
        digest.approved = True
        digest.sent = False
        digest.unresolved = unresolved
        if profile.whatsapp_consent and profile.phone_number:
            send_result = self._log_tool(
                send_whatsapp_digest(profile.phone_number, self._digest_text(digest))
            )
            digest.sent = bool(send_result.success)
        self.db.save_digest_history(self.current_user_id, digest)
        self.current_digest = digest
        return digest

    def _collect_events(self, profile: UserProfile) -> tuple[List[Event], List[str]]:
        self._trace(
            "plan_tool_calls",
            "Planned source lookups for teams and athletes.",
            metadata={
                "teams": [team.name for team in profile.teams],
                "athletes": [athlete.name for athlete in profile.athletes],
            },
            persist=bool(self.current_user_id),
        )
        events: List[Event] = []
        unresolved: List[str] = []

        for team in profile.teams:
            normalized = self._log_tool(normalize_sports_entity(team.name))
            canonical_name = team.name
            sport = team.sport
            if normalized.success:
                normalized_entity = normalized.data["entity"]
                canonical_name = normalized_entity.name
                sport = normalized_entity.sport
                team.external_id = normalized_entity.external_id

            team_events = self._collect_team_events(canonical_name, sport)

            if team_events:
                events.extend(team_events)
            else:
                unresolved.append(team.name)

        for athlete in profile.athletes:
            normalized = self._log_tool(normalize_sports_entity(athlete.name))
            canonical_name = (
                normalized.data["canonical_name"] if normalized.success else athlete.name
            )
            athlete_result = self._log_tool(web_search_event_source(canonical_name))
            if athlete_result.success:
                events.extend(athlete_result.data["events"])
            else:
                unresolved.append(athlete.name)

        return events, unresolved

    def _collect_team_events(self, canonical_name: str, sport: str) -> List[Event]:
        if sport == "soccer":
            soccer_result = self._log_tool(search_soccer_fixture_apifootball(canonical_name))
            if soccer_result.success:
                return soccer_result.data["events"]

            sportsdb_events = self._collect_sportsdb_team_events(canonical_name)
            if sportsdb_events:
                return sportsdb_events
            return self._web_fallback_events(canonical_name)

        sportsdb_events = self._collect_sportsdb_team_events(canonical_name)
        if sportsdb_events:
            return sportsdb_events
        return self._web_fallback_events(canonical_name)

    def _collect_sportsdb_team_events(self, canonical_name: str) -> List[Event]:
        search_result = self._log_tool(search_team_thesportsdb(canonical_name))
        if not search_result.success:
            return []

        event_result = self._get_next_team_events_with_retry(search_result.data["team_id"])
        if event_result.success:
            return event_result.data["events"]
        return []

    def _get_next_team_events_with_retry(self, team_id: str) -> ToolResult:
        first_result = self._log_tool(get_next_team_events_thesportsdb(team_id))
        if first_result.success:
            return first_result
        return self._log_tool(get_next_team_events_thesportsdb(team_id))

    def _web_fallback_events(self, canonical_name: str) -> List[Event]:
        fallback_result = self._log_tool(web_search_event_source(canonical_name))
        if fallback_result.success:
            return fallback_result.data["events"]
        return []

    def _confirm_preferences_response(self) -> AgentResponse:
        profile = self._require_profile()
        return self._response(
            f"Please confirm preferences for {profile.name} before I build the digest.",
            "confirm_preferences",
        )

    def _response(self, message: str, requires_action: str) -> AgentResponse:
        return AgentResponse(
            message=message,
            requires_action=requires_action,
            profile=self.current_profile,
            digest=self.current_digest,
            trace=list(self.trace),
        )

    def _trace(
        self,
        step: str,
        message: str,
        tool_name: Optional[str] = None,
        metadata: Optional[dict] = None,
        persist: bool = False,
    ) -> TraceEntry:
        entry = TraceEntry(
            step=step,
            message=message,
            tool_name=tool_name,
            metadata=metadata or {},
        )
        self.trace.append(entry)
        if persist and self.current_user_id is not None:
            self.db.log_trace(self.current_user_id, entry)
        return entry

    def _log_tool(self, result: ToolResult) -> ToolResult:
        if self.current_user_id is not None:
            self.db.log_tool_run(self.current_user_id, result)
        self._trace(
            "tool_run",
            f"Ran {result.tool_name}.",
            tool_name=result.tool_name,
            metadata={"success": result.success, "error": result.error},
            persist=bool(self.current_user_id),
        )
        return result

    def _ensure_user_id(self, profile: UserProfile) -> int:
        if self.current_user_id is None:
            self.current_user_id = self.db.save_user_preferences(profile)
            profile.user_id = str(self.current_user_id)
        return self.current_user_id

    def _require_profile(self) -> UserProfile:
        if self.current_profile is None:
            raise RuntimeError("No active FanPulse profile. Start with handle_user_message().")
        return self.current_profile

    def _require_digest(self) -> Digest:
        if self.current_digest is None:
            raise RuntimeError("No digest is awaiting approval.")
        return self.current_digest

    def _digest_text(self, digest: Digest) -> str:
        event_lines = [f"- {event.title}" for event in digest.events]
        return "\n".join([digest.title, digest.summary or "", *event_lines])
