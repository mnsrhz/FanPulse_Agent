from __future__ import annotations


def should_accept_user_message(messages: list[dict[str, str]], text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False

    latest_user_message = None
    for message in reversed(messages):
        if message.get("role") == "user":
            latest_user_message = message.get("content", "").strip()
            break

    return latest_user_message != normalized
