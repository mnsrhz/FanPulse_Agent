from __future__ import annotations

import os
from typing import Any, Optional

import requests

SERPAPI_BASE_URL = "https://serpapi.com/search.json"

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


class SerpAPIClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = SERPAPI_BASE_URL,
        timeout: float = 8.0,
    ):
        self.api_key = api_key or os.environ.get("SERPAPI_API_KEY") or ""
        self.base_url = base_url
        self.timeout = timeout
        self.last_errors: Any = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str) -> list[dict[str, Any]]:
        if not self.enabled:
            self.last_errors = {"auth": "SERPAPI_API_KEY is not configured."}
            return []
        response = requests.get(
            self.base_url,
            params={"engine": "google", "q": query, "api_key": self.api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            self.last_errors = {"payload": "Provider returned a non-object response."}
            return []
        self.last_errors = payload.get("error")
        organic = payload.get("organic_results")
        if not isinstance(organic, list):
            return []
        return [item for item in organic if isinstance(item, dict)]
