from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

from fanpulse_agent.agent_planner import plan_digest_tool_calls, plan_next_agent_action
from fanpulse_agent.database import FanPulseDB
from fanpulse_agent.entity_extraction import extract_profile_from_text
from fanpulse_agent.models import Digest, Event, SportsEntity, ToolResult, TraceEntry, UserProfile
from fanpulse_agent.tools import (
    discover_official_schedule_sources,
    extract_official_schedule_events,
    generate_digest,
    get_next_league_events_thesportsdb,
    get_next_league_fixtures_apifootball,
    get_next_races_apiformula1,
    get_team_games_apibasketball,
    get_next_team_events_thesportsdb,
    normalize_sports_entity,
    rank_events,
    search_driver_apiformula1,
    search_sports_events_serpapi,
    search_soccer_fixture_apifootball,
    search_league_thesportsdb,
    search_league_apifootball,
    search_player_thesportsdb,
    search_team_apibasketball,
    search_team_thesportsdb,
    send_whatsapp_digest,
    validate_official_schedule_events,
    web_search_event_source,
    is_upcoming_event,
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
        if self.current_profile is not None and self.current_digest is None:
            self._merge_profile_update(profile)
            return self._planned_next_response(text)

        if self.current_profile is not None and self.current_digest is not None:
            if profile.phone_number and not self._is_whatsapp_refusal(text):
                profile.whatsapp_consent = True
            self._merge_profile_update(profile)
            self._trace(
                "update_contact",
                "Updated contact details without discarding the pending digest.",
                metadata={
                    "has_phone": bool(self.current_profile.phone_number),
                    "has_consent": self.current_profile.whatsapp_consent,
                },
                persist=bool(self.current_user_id),
            )
            if self.current_user_id is not None:
                self.db.save_user_preferences(self.current_profile)
            return self._planned_next_response(text)

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

        return self._planned_next_response(text)

    def _merge_profile_update(self, update: UserProfile) -> None:
        profile = self._require_profile()
        if update.name and update.name != "Fan":
            profile.name = update.name
        if update.name_provided:
            profile.name_provided = True
        if update.phone_number:
            profile.phone_number = update.phone_number
        if update.timezone_provided:
            profile.timezone = update.timezone
            profile.timezone_provided = True
        elif update.timezone and update.timezone != "America/Los_Angeles":
            profile.timezone = update.timezone
        if update.schedule_provided:
            profile.digest_schedule = update.digest_schedule
            profile.schedule_provided = True
        elif update.digest_schedule and update.digest_schedule != "Friday morning":
            profile.digest_schedule = update.digest_schedule
        if update.whatsapp_consent:
            profile.whatsapp_consent = True
        if update.teams:
            profile.teams = update.teams
            profile.favorite_teams = update.teams
        if update.athletes:
            profile.athletes = update.athletes
        if update.leagues:
            profile.leagues = update.leagues
        if update.sports:
            profile.sports = update.sports
            profile.favorite_sports = update.sports
        if update.clarification_choices:
            profile.clarification_choices.update(update.clarification_choices)

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

        if not self._profile_can_receive_whatsapp(profile):
            self._trace(
                "send_blocked",
                "WhatsApp send blocked because consent or phone number is missing.",
                metadata={
                    "has_consent": profile.whatsapp_consent,
                    "has_phone": bool(profile.phone_number),
                },
                persist=bool(self.current_user_id),
            )
            return self._missing_contact_response()

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
        tool_plan = plan_digest_tool_calls(profile)
        self._trace(
            "llm_plan_tool_calls",
            "LLM planned source lookups for teams and athletes.",
            metadata={
                "tools": tool_plan.tools,
                "reasoning": tool_plan.reasoning,
                "teams": [team.name for team in profile.teams],
                "athletes": [athlete.name for athlete in profile.athletes],
                "leagues": [league.name for league in profile.leagues],
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

            future_team_events = self._future_events(team_events)
            next_event = self._next_event(future_team_events)
            if next_event:
                events.append(next_event)
            else:
                unresolved.append(team.name)

        for athlete in profile.athletes:
            official_events = self._official_schedule_events(
                athlete.name, athlete.sport, athlete.entity_type or "athlete"
            )
            next_event = self._next_event(official_events)
            if next_event:
                events.append(next_event)
                continue

            if athlete.sport == "formula 1":
                driver_result = self._log_tool(search_driver_apiformula1(athlete.name))
                race_result = self._log_tool(get_next_races_apiformula1(athlete.name))
                race_events = (
                    self._future_events(race_result.data["events"])
                    if race_result.success
                    else []
                )
                next_event = self._next_event(race_events)
                if next_event:
                    events.append(next_event)
                    continue
                serp_result = self._log_tool(
                    search_sports_events_serpapi(athlete.name, athlete.sport)
                )
                serp_events = (
                    self._future_events(serp_result.data["events"])
                    if serp_result.success
                    else []
                )
                next_event = self._next_event(serp_events)
                if next_event:
                    events.append(next_event)
                    continue

            athlete_result = self._log_tool(search_player_thesportsdb(athlete.name))
            athlete_events = (
                self._future_events(athlete_result.data["events"])
                if athlete_result.success
                else []
            )
            next_event = self._next_event(athlete_events)
            if next_event:
                events.append(next_event)
            else:
                fallback_result = self._log_tool(web_search_event_source(athlete.name))
                fallback_events = (
                    self._future_events(fallback_result.data["events"])
                    if fallback_result.success
                    else []
                )
                next_event = self._next_event(fallback_events)
                if next_event:
                    events.append(next_event)
                else:
                    unresolved.append(athlete.name)

        for league in profile.leagues:
            official_events = self._official_schedule_events(
                league.name, league.sport, league.entity_type or "league"
            )
            next_event = self._next_event(official_events)
            if next_event:
                events.append(next_event)
                continue

            if league.sport == "soccer":
                api_league = self._log_tool(search_league_apifootball(league.name))
                if api_league.success:
                    league.external_id = str(api_league.data["league_id"])
                    api_fixtures = self._log_tool(
                        get_next_league_fixtures_apifootball(
                            api_league.data["league_id"],
                            api_league.data["name"],
                        )
                    )
                    api_events = (
                        self._future_events(api_fixtures.data["events"])
                        if api_fixtures.success
                        else []
                    )
                    next_event = self._next_event(api_events)
                    if next_event:
                        events.append(next_event)
                        continue

            league_result = self._log_tool(search_league_thesportsdb(league.name))
            if not league_result.success:
                unresolved.append(league.name)
                continue
            league.external_id = league_result.data["league_id"]
            events_result = self._log_tool(
                get_next_league_events_thesportsdb(
                    league_result.data["league_id"],
                    league_result.data["name"],
                )
            )
            league_events = (
                self._future_events(events_result.data["events"])
                if events_result.success
                else []
            )
            next_event = self._next_event(league_events)
            if next_event:
                events.append(next_event)
            else:
                unresolved.append(league.name)

        if not profile.teams and not profile.athletes and not profile.leagues:
            for sport in profile.sports:
                official_events = self._official_schedule_events(
                    sport.title() if sport.lower() != "formula 1" else "Formula 1",
                    sport,
                    "sport",
                )
                next_event = self._next_event(official_events)
                if next_event:
                    events.append(next_event)
                else:
                    unresolved.append(sport)

        return events, unresolved

    def _collect_team_events(self, canonical_name: str, sport: str) -> List[Event]:
        official_events = self._official_schedule_events(canonical_name, sport, "team")
        if official_events:
            return official_events

        if sport == "soccer":
            soccer_result = self._log_tool(search_soccer_fixture_apifootball(canonical_name))
            if soccer_result.success:
                return soccer_result.data["events"]

            sportsdb_events = self._collect_sportsdb_team_events(canonical_name)
            if sportsdb_events:
                return sportsdb_events
            return self._web_fallback_events(canonical_name)

        if sport == "basketball":
            team_result = self._log_tool(search_team_apibasketball(canonical_name))
            if team_result.success:
                games_result = self._log_tool(
                    get_team_games_apibasketball(
                        team_result.data["team_id"],
                        team_result.data["name"],
                    )
                )
                if games_result.success:
                    return games_result.data["events"]

            sportsdb_events = self._collect_sportsdb_team_events(canonical_name)
            if sportsdb_events:
                return sportsdb_events
            serp_result = self._log_tool(
                search_sports_events_serpapi(canonical_name, sport)
            )
            if serp_result.success:
                return serp_result.data["events"]
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

    def _official_schedule_events(
        self, entity_name: str, sport: str, entity_type: str
    ) -> List[Event]:
        sources_result = self._log_tool(
            discover_official_schedule_sources(entity_name, sport, entity_type)
        )
        if not sources_result.success:
            return []

        events_result = self._log_tool(
            extract_official_schedule_events(
                entity_name,
                sport,
                sources_result.data.get("sources", []),
            )
        )
        if not events_result.success:
            return []

        validated_result = self._log_tool(
            validate_official_schedule_events(events_result.data.get("events", []))
        )
        if not validated_result.success:
            return []
        return validated_result.data["events"]

    def _future_events(self, events: List[Event]) -> List[Event]:
        return [event for event in events if is_upcoming_event(event)]

    def _next_event(self, events: List[Event]) -> Optional[Event]:
        if not events:
            return None
        return sorted(events, key=self._event_sort_key)[0]

    def _event_sort_key(self, event: Event) -> tuple:
        if not event.start_time:
            return (date.max, event.title)
        try:
            event_date = datetime.fromisoformat(event.start_time).date()
        except ValueError:
            try:
                event_date = date.fromisoformat(event.start_time[:10])
            except ValueError:
                event_date = date.max
        return (event_date, event.start_time or "", event.title)

    def _planned_next_response(self, user_message: str) -> AgentResponse:
        profile = self._require_profile()
        missing_fields = self._missing_profile_fields(profile)
        plan = plan_next_agent_action(
            user_message=user_message,
            profile=profile,
            has_pending_digest=self.current_digest is not None,
            ambiguous_entities=self._ambiguous_entities,
            missing_fields=missing_fields,
            contact_ready=self._profile_can_receive_whatsapp(profile),
        )
        self._trace(
            "llm_plan_next_action",
            "LLM selected the next safe conversational action.",
            metadata={
                "next_action": plan.next_action,
                "reasoning": plan.reasoning,
                "tool_plan": plan.tool_plan,
                "missing_fields": list(missing_fields),
            },
            persist=bool(self.current_user_id),
        )

        if plan.next_action == "collect_profile_details":
            return self._profile_details_response(plan.assistant_message)
        if plan.next_action == "collect_preferences":
            return self._collect_preferences_response(plan.assistant_message)
        if plan.next_action == "clarify_ambiguity":
            return self._clarify_ambiguity_response(plan.assistant_message)
        if plan.next_action == "collect_contact":
            return self._missing_contact_response(plan.assistant_message)
        if plan.next_action == "approve_digest":
            return self._approval_prompt_response(plan.assistant_message)
        if plan.next_action == "complete":
            return self._response(plan.assistant_message or "Done.", "complete")
        return self._confirm_preferences_response(plan.assistant_message)

    def _confirm_preferences_response(
        self, message_override: Optional[str] = None
    ) -> AgentResponse:
        profile = self._require_profile()
        return self._response(
            message_override
            or f"Please confirm preferences for {profile.name} before I build the digest.",
            "confirm_preferences",
        )

    def _collect_preferences_response(
        self, message_override: Optional[str] = None
    ) -> AgentResponse:
        return self._response(
            message_override
            or (
                "Which teams, athletes, or sports should I track in your weekly digest?"
            ),
            "collect_preferences",
        )

    def _clarify_ambiguity_response(
        self, message_override: Optional[str] = None
    ) -> AgentResponse:
        names = ", ".join(entity.name for entity in self._ambiguous_entities)
        return self._response(
            message_override
            or f"Please clarify this preference before I continue: {names}.",
            "clarify_ambiguity",
        )

    def _missing_profile_fields(self, profile: UserProfile) -> list[str]:
        missing = []
        if not profile.name_provided or profile.name == "Fan":
            missing.append("name")
        if not profile.timezone_provided:
            missing.append("timezone")
        if not profile.schedule_provided:
            missing.append("frequency")
        return missing

    def _profile_details_response(
        self, message_override: Optional[str] = None
    ) -> AgentResponse:
        profile = self._require_profile()
        missing = self._missing_profile_fields(profile)
        if missing == ["name"]:
            message = "What name should I save for this FanPulse digest?"
        elif missing == ["timezone"]:
            message = (
                f"Thanks, {profile.name}. What timezone should I use for your digest schedule?"
            )
        elif missing == ["frequency"]:
            message = "What update frequency should I use for sports notifications?"
        else:
            message = (
                "Before I save your preferences, what name, timezone, and update "
                "frequency should I use for your digest?"
            )
        return self._response(message_override or message, "collect_profile_details")

    def _profile_can_receive_whatsapp(self, profile: UserProfile) -> bool:
        return bool(profile.whatsapp_consent and profile.phone_number)

    def _is_whatsapp_refusal(self, text: str) -> bool:
        normalized = text.lower()
        refusal_markers = (
            "do not send",
            "don't send",
            "no whatsapp",
            "not whatsapp",
        )
        return "whatsapp" in normalized and any(
            marker in normalized for marker in refusal_markers
        )

    def _missing_contact_response(
        self, message_override: Optional[str] = None
    ) -> AgentResponse:
        profile = self._require_profile()
        if profile.phone_number and not profile.whatsapp_consent:
            message = (
                "I have your phone number. Please confirm you want this sent on WhatsApp."
            )
        elif profile.whatsapp_consent and not profile.phone_number:
            message = "I have WhatsApp consent. Please share the phone number to send it to."
        else:
            message = "I need WhatsApp consent and a phone number before sending."
        return self._response(message_override or message, "collect_contact")

    def _approval_prompt_response(
        self, message_override: Optional[str] = None
    ) -> AgentResponse:
        return self._response(
            message_override
            or "Thanks, I updated your WhatsApp details. Please approve the digest when ready.",
            "approve_digest",
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
        lines = ["FanPulse digest"]
        if digest.events:
            for event in digest.events:
                candidate = self._compact_whatsapp_event_line(event)
                candidate_text = "\n".join([*lines, candidate])
                if len(candidate_text) <= 360:
                    lines.append(candidate)
                else:
                    break
            hidden_count = max(0, len(digest.events) - (len(lines) - 1))
            if hidden_count:
                lines.append(f"+{hidden_count} more in app")
        else:
            lines.append("No confirmed upcoming events.")

        if digest.unresolved:
            unresolved = ", ".join(digest.unresolved[:2])
            candidate = f"Review: {unresolved}"
            if len("\n".join([*lines, candidate])) <= 380:
                lines.append(candidate)

        text = "\n".join(lines)
        if len(text) <= 400:
            return text
        return text[:397].rstrip() + "..."

    def _compact_whatsapp_event_line(self, event: Event) -> str:
        icon = event.sport_icon or "•"
        display_time = event.display_time or event.start_time or "Time TBD"
        source = event.source_url or "mock://fanpulse-agent"
        return f"{icon} {event.title} — {display_time}\n{source}"

    def _whatsapp_event_lines(self, index: int, event: Event) -> List[str]:
        league = event.metadata.get("league") or event.entities[0].league if event.entities else ""
        sport = event.metadata.get("sport") or event.entities[0].sport if event.entities else ""
        display_time = event.display_time or event.start_time or "Time TBD"
        source = event.source_url or "mock://fanpulse-agent"
        mode_label = "mock mode" if event.mock else "live source"
        status_label = "incomplete" if event.incomplete else "complete"
        opponent = f" vs {event.opponent}" if event.opponent else ""
        icon = event.sport_icon or "•"
        return [
            "",
            f"{index}. {icon} {event.title}",
            f"   Time: {display_time}",
            f"   Team/Athlete: {event.entity_name or 'FanPulse'}{opponent}",
            f"   League: {league or 'Unknown'}",
            f"   Sport: {sport or 'sport'}",
            f"   Source: {source}",
            f"   confidence {event.confidence:.0%} · {mode_label} · {status_label}",
        ]
