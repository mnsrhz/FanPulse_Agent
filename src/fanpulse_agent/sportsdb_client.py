from __future__ import annotations

import os
from typing import Any, Optional

import requests

SPORTSDB_BASE_URL = "https://www.thesportsdb.com/api/v1/json"

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


class SportsDBClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = SPORTSDB_BASE_URL,
        timeout: float = 8.0,
    ):
        self.api_key = api_key or os.environ.get("THESPORTSDB_API_KEY") or ""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def search_team(self, name: str) -> Optional[dict[str, Any]]:
        payload = self._get("searchteams.php", {"t": name})
        teams = payload.get("teams") if isinstance(payload, dict) else None
        return self._first(teams)

    def next_team_events(self, team_id: str) -> list[dict[str, Any]]:
        payload = self._get("eventsnext.php", {"id": team_id})
        return self._list(payload.get("events") if isinstance(payload, dict) else None)

    def search_player(self, name: str) -> Optional[dict[str, Any]]:
        payload = self._get("searchplayers.php", {"p": name})
        players = (
            payload.get("player") or payload.get("players")
            if isinstance(payload, dict)
            else None
        )
        return self._first(players)

    def player_results(self, player_id: str) -> list[dict[str, Any]]:
        payload = self._get("playerresults.php", {"id": player_id})
        return self._list(payload.get("results") if isinstance(payload, dict) else None)

    def search_league(self, name: str) -> Optional[dict[str, Any]]:
        payload = self._get("all_leagues.php", {})
        leagues = self._list(payload.get("leagues") if isinstance(payload, dict) else None)
        normalized = _normalize_name(name)
        for league in leagues:
            if _normalize_name(str(league.get("strLeague") or "")) == normalized:
                return league
        for league in leagues:
            if normalized in _normalize_name(str(league.get("strLeague") or "")):
                return league
        return None

    def next_league_events(self, league_id: str) -> list[dict[str, Any]]:
        payload = self._get("eventsnextleague.php", {"id": league_id})
        return self._list(payload.get("events") if isinstance(payload, dict) else None)

    def _get(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if not self.enabled:
            return {}
        response = requests.get(
            f"{self.base_url}/{self.api_key}/{endpoint}",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _first(self, value: Any) -> Optional[dict[str, Any]]:
        values = self._list(value)
        return values[0] if values else None

    def _list(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]


def _normalize_name(value: str) -> str:
    return " ".join(value.lower().split())
