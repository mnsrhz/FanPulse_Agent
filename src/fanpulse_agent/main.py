"""Main entrypoint for the FanPulse Agent."""

import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WHATSAPP_WEBHOOK_URL = os.getenv("WHATSAPP_WEBHOOK_URL")


def generate_weekly_digest() -> str:
    """Generate a weekly sponsor digest summary."""
    # TODO: replace this stub with actual data aggregation and summary generation
    return (
        "FanPulse Weekly Sponsor Digest:\n"
        "- Sponsor A: campaign update\n"
        "- Sponsor B: new offer details\n"
        "- Sponsor C: engagement highlights\n"
    )


def send_whatsapp_message(message: str) -> None:
    """Send the generated digest to WhatsApp via webhook or API."""
    if not WHATSAPP_WEBHOOK_URL:
        raise ValueError("WHATSAPP_WEBHOOK_URL is not configured")

    print(f"Sending WhatsApp message to {WHATSAPP_WEBHOOK_URL}...")
    print(message)
    # TODO: implement WhatsApp API/webhook integration here


def main() -> None:
    """Run the agent workflow."""
    if not OPENAI_API_KEY:
        print("Warning: OPENAI_API_KEY is not configured.")

    digest = generate_weekly_digest()
    send_whatsapp_message(digest)


if __name__ == "__main__":
    main()
