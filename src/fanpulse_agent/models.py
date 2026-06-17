from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SportsEntity:
    name: str
    entity_type: str
    sport: str
    source_text: str = ""
    confidence: float = 0.9
    needs_clarification: bool = False
    clarification_prompt: Optional[str] = None
    league: Optional[str] = None
    external_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UserProfile:
    name: str = "Fan"
    phone_number: Optional[str] = None
    timezone: str = "America/Los_Angeles"
    digest_schedule: str = "Friday morning"
    whatsapp_consent: bool = False
    name_provided: bool = False
    timezone_provided: bool = False
    schedule_provided: bool = False
    teams: List[SportsEntity] = field(default_factory=list)
    athletes: List[SportsEntity] = field(default_factory=list)
    leagues: List[SportsEntity] = field(default_factory=list)
    sports: List[str] = field(default_factory=list)
    clarification_choices: Dict[str, Any] = field(default_factory=dict)
    user_id: Optional[str] = None
    favorite_teams: List[SportsEntity] = field(default_factory=list)
    favorite_sports: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["teams"] = [team.to_dict() for team in self.teams]
        data["athletes"] = [athlete.to_dict() for athlete in self.athletes]
        data["leagues"] = [league.to_dict() for league in self.leagues]
        data["favorite_teams"] = [team.to_dict() for team in self.favorite_teams]
        return data


@dataclass
class Event:
    title: str
    event_type: str
    start_time: Optional[str] = None
    sport_icon: str = ""
    opponent: Optional[str] = None
    display_time: Optional[str] = None
    confidence: float = 0.9
    mock: bool = False
    incomplete: bool = False
    entities: List[SportsEntity] = field(default_factory=list)
    source_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    entity_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["entities"] = [entity.to_dict() for entity in self.entities]
        return data


@dataclass
class Digest:
    user_id: str
    title: str
    events: List[Event] = field(default_factory=list)
    generated_at: str = field(default_factory=utc_now_iso)
    summary: Optional[str] = None
    approved: bool = False
    sent: bool = False
    unresolved: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["events"] = [event.to_dict() for event in self.events]
        return data


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    data: Any = None
    source_url: Optional[str] = None
    error: Optional[str] = None
    confidence: Optional[float] = None
    mock: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TraceEntry:
    step: str
    message: str
    timestamp: str = field(default_factory=utc_now_iso)
    tool_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
