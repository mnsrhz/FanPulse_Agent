from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SportsEntity:
    name: str
    entity_type: str
    sport: Optional[str] = None
    league: Optional[str] = None
    external_id: Optional[str] = None
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UserProfile:
    user_id: str
    name: Optional[str] = None
    favorite_teams: List[SportsEntity] = field(default_factory=list)
    favorite_sports: List[str] = field(default_factory=list)
    timezone: str = "UTC"
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["favorite_teams"] = [team.to_dict() for team in self.favorite_teams]
        return data


@dataclass
class Event:
    title: str
    event_type: str
    start_time: Optional[str] = None
    entities: List[SportsEntity] = field(default_factory=list)
    source_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

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
