from fanpulse_agent.ui_state import should_accept_user_message


def test_rejects_immediate_duplicate_user_message_after_assistant_response():
    messages = [
        {"role": "assistant", "content": "Tell me who you follow."},
        {"role": "user", "content": "I follow Arsenal and Real Madrid."},
        {"role": "assistant", "content": "What name and timezone should I use?"},
    ]

    assert should_accept_user_message(messages, "I follow Arsenal and Real Madrid.") is False


def test_accepts_same_text_when_it_is_not_the_latest_user_turn():
    messages = [
        {"role": "assistant", "content": "Tell me who you follow."},
        {"role": "user", "content": "Yes"},
        {"role": "assistant", "content": "Please confirm WhatsApp."},
        {"role": "user", "content": "No"},
        {"role": "assistant", "content": "Okay, no WhatsApp."},
    ]

    assert should_accept_user_message(messages, "Yes") is True
