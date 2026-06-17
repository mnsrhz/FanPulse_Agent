from __future__ import annotations

import os
from typing import Any, Optional

import requests

TWILIO_API_BASE_URL = "https://api.twilio.com/2010-04-01"

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


class TwilioWhatsAppClient:
    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        whatsapp_from: Optional[str] = None,
        base_url: str = TWILIO_API_BASE_URL,
        timeout: float = 10.0,
    ):
        self.account_sid = account_sid or os.environ.get("TWILIO_ACCOUNT_SID") or ""
        self.auth_token = auth_token or os.environ.get("TWILIO_AUTH_TOKEN") or ""
        self.whatsapp_from = whatsapp_from or os.environ.get("TWILIO_WHATSAPP_FROM") or ""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.whatsapp_from)

    def send_message(self, to_number: str, body: str) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError(
                "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_WHATSAPP_FROM are required."
            )
        response = requests.post(
            f"{self.base_url}/Accounts/{self.account_sid}/Messages.json",
            data={
                "From": self._whatsapp_address(self.whatsapp_from),
                "To": self._whatsapp_address(to_number),
                "Body": body,
            },
            auth=(self.account_sid, self.auth_token),
            timeout=self.timeout,
        )
        try:
            response.raise_for_status()
        except Exception as exc:
            details = getattr(response, "text", "")
            detail_suffix = f": {details}" if details else ""
            raise RuntimeError(f"{exc}{detail_suffix}") from exc
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _whatsapp_address(self, value: str) -> str:
        text = value.strip()
        if text.startswith("whatsapp:"):
            return text
        if not text.startswith("+"):
            text = f"+{text}"
        return f"whatsapp:{text}"
