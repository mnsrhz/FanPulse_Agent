# FanPulse AI

FanPulse AI is a mock-first sports digest agent that onboards a fan through chat, builds a weekly event preview, and approval-gates the WhatsApp send step.

## What It Does

- Extracts favorite teams, athletes, sports, schedule, phone number, and WhatsApp consent from a short onboarding message.
- Handles ambiguous preferences such as India Cricket before saving preferences.
- Generates a digest preview from structured mock tool calls.
- Logs agent trace and MCP-style tool names to SQLite for debugging.
- Runs locally without provider API keys.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run The Streamlit App

```bash
PYTHONPATH=src streamlit run app.py
```

If you are using the project virtual environment directly:

```bash
PYTHONPATH=src .venv/bin/streamlit run app.py
```

The app opens a dark, chat-first FanPulse AI workspace with profile cards, digest preview cards, approval buttons, and a collapsed Agent Trace / Debug View.

## Sample Onboarding Text

Paste this into the chat, or use the sample onboarding button in the app:

```text
I am Mansoor. I follow the Lakers, Real Madrid, India cricket, Novak Djokovic and Max Verstappen. Send my digest every Friday morning to +14155550123 on WhatsApp.
```

Expected flow:

1. Choose the India Cricket clarification.
2. Confirm preferences.
3. Review the digest preview.
4. Approve and send the digest.

WhatsApp sending is mocked, so no message is actually delivered.

## Mock Mode And API Keys

FanPulse AI runs in mock mode by default. Missing API keys are fine for local development because the current sports lookups, web search, ranking, digest generation, and WhatsApp send use deterministic mock tool results.

For later live integrations, copy `.env.example` and fill in provider credentials:

```bash
cp .env.example .env
```

`.env.example` includes placeholders for TheSportsDB, API-Football, SerpAPI, Twilio WhatsApp, and `FANPULSE_DB_PATH`.

## Tests

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=.pycache python3 -m compileall app.py src
PYTHONPATH=src .venv/bin/python -m pytest tests/test_entity_extraction.py tests/test_agent_flow.py -v
```

## Project Structure

- `app.py` - Streamlit chat UI.
- `src/fanpulse_agent/agent.py` - onboarding, approval gates, digest flow, and trace orchestration.
- `src/fanpulse_agent/database.py` - SQLite persistence for profiles, digest history, tool runs, and traces.
- `src/fanpulse_agent/entity_extraction.py` - deterministic onboarding extraction.
- `src/fanpulse_agent/tools.py` - mock-first tools with MCP-style names.
- `tests/` - extraction, database, tool, and agent flow coverage.
