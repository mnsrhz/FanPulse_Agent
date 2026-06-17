from pathlib import Path


COMPONENT_HTML = Path("components/fanpulse_phone/index.html")


def test_phone_component_optimistically_echoes_submitted_prompt():
    html = COMPONENT_HTML.read_text()

    assert "appendOptimisticUserMessage(prompt)" in html
    assert "data-fp-optimistic" in html


def test_phone_component_refocuses_input_after_render():
    html = COMPONENT_HTML.read_text()

    assert "focusInputSoon()" in html
    assert "shouldRefocusInput" in html


def test_phone_component_shows_processing_indicator_after_submit():
    html = COMPONENT_HTML.read_text()

    assert "appendProcessingIndicator()" in html
    assert "data-fp-processing" in html
    assert "Agent is thinking" in html


def test_phone_component_shows_processing_indicator_after_action_click():
    html = COMPONENT_HTML.read_text()

    assert 'event.target.closest("[data-fp-action]")' in html
    assert 'appendProcessingIndicator("Agent is working")' in html
    assert "actionButton.disabled = true" in html
