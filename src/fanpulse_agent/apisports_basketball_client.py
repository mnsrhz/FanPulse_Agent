from __future__ import annotations

import os
from typing import Any, Optional

import requests

APISPORTS_BASKETBALL_BASE_URL = "https://v1.basketball.api-sports.io"

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


class APISportsBasketballClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = APISPORTS_BASKETBALL_BASE_URL,
        timeout: float = 8.0,
    ):
        self.api_key = (
            api_key
            or os.environ.get("APISPORTS_BASKETBALL_API_KEY")
            or os.environ.get("APIFOOTBALL_API_KEY")
            or ""
        )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.last_errors: Any = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def search_team(self, name: str) -> Optional[dict[str, Any]]:
        payload = self._get("teams", {"search": name})
        return self._first(payload.get("response") if isinstance(payload, dict) else None)

    def next_team_games(self, team_id: int) -> list[dict[str, Any]]:
        payload = self._get("games", {"team": str(team_id), "next": "5"})
        return self._list(payload.get("response") if isinstance(payload, dict) else None)

    def search_league(self, name: str) -> Optional[dict[str, Any]]:
        payload = self._get("leagues", {"search": name})
        return self._first(payload.get("response") if isinstance(payload, dict) else None)

    def next_league_games(self, league_id: int) -> list[dict[str, Any]]:
        payload = self._get("games", {"league": str(league_id), "next": "5"})
        return self._list(payload.get("response") if isinstance(payload, dict) else None)

    def _get(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if not self.enabled:
            self.last_errors = {"auth": "APISPORTS_BASKETBALL_API_KEY is not configured."}
            return {}
        response = requests.get(
            f"{self.base_url}/{endpoint}",
            headers={"x-apisports-key": self.api_key},
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            self.last_errors = {"payload": "Provider returned a non-object response."}
            return {}
        self.last_errors = payload.get("errors")
        return payload

    def _first(self, value: Any) -> Optional[dict[str, Any]]:
        values = self._list(value)
        return values[0] if values else None

    def _list(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]
