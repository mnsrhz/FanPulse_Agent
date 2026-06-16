# FanPulse AI Streamlit App Design

Date: 2026-06-16

## Goal

Build a Streamlit app called FanPulse AI for an Agentic AI course assignment. The app lets a sports fan onboard conversationally, records favorite teams, athletes, and sports, finds upcoming events, generates a weekly digest with source links, and asks for approval before WhatsApp delivery.

The first implementation is mock-first so the demo is reliable without API keys. The code must still expose provider boundaries that can later be connected to real sports APIs, Twilio, or MCP servers without changing the user flow.

## UX Direction

The app follows the attached clickable HTML prototype:

- Dark, polished SaaS dashboard feel.
- Two-column desktop layout with responsive stacking on smaller screens.
- Left side: FanPulse identity, short product context, user/profile status, and optional controls.
- Right side: chat-first agent surface using `st.chat_message()` and `st.chat_input()`.
- Quick action buttons for sample onboarding, ambiguity choices, preference confirmation, digest approval, and manual weekly run.
- Digest preview cards with sport icons, event details, source links, and confidence labels.
- Hidden "Agent Trace / Debug View" expander for instructor review.

The app must not become a long form. Forms are limited to compact confirmations and controls that support the chat flow.

## Architecture

Use a small Python package under `src/fanpulse_agent/` plus top-level Streamlit and job entry points:

- `app.py`: Streamlit UI, session state orchestration, CSS, chat rendering, user actions, manual weekly trigger.
- `src/fanpulse_agent/models.py`: dataclasses for user profile, sports entities, events, digests, tool results, and trace entries.
- `src/fanpulse_agent/database.py`: SQLite schema creation and persistence helpers.
- `src/fanpulse_agent/entity_extraction.py`: mock entity extraction and normalization with replaceable LLM-ready interface.
- `src/fanpulse_agent/tools.py`: required tool functions, mock provider data, retry/fallback helpers, and structured tool result creation.
- `src/fanpulse_agent/agent.py`: planner, tool selection, HITL state transitions, digest generation, error recovery, and trace logging.
- `weekly_digest_job.py`: separate local recurring-job entry point that can be run manually or by cron.
- `.env.example`: documented environment variables for future real providers.

The existing `src/fanpulse_agent/main.py` can remain as a simple CLI wrapper or be updated to call the weekly job flow. It must not be the primary Streamlit entry point.

## Agent And Tool Design

The agent uses a mock-first, MCP-ready tool boundary. Each tool has a stable tool name, structured inputs, and a structured JSON-like output:

- `success`
- `data`
- `source_url`
- `error`
- `confidence`
- `mock`

Required tool functions:

- `search_team_thesportsdb(entity_name)`
- `get_next_team_events_thesportsdb(team_id)`
- `search_soccer_fixture_apifootball(entity_name)`
- `web_search_event_source(entity_name)`
- `normalize_sports_entity(entity_name)`
- `rank_events(events, user_preferences)`
- `generate_digest(events, user_profile)`
- `send_whatsapp_digest(phone_number, digest_text)`
- `save_user_preferences(user_profile)`
- `save_digest_history(user_id, digest)`

The planner chooses tools with this logic:

- Team or league lookup uses TheSportsDB-style mock tools.
- Soccer fallback uses API-Football-style mock tools.
- Athlete or unclear event lookup uses web-search-style mock tools.
- WhatsApp delivery uses Twilio-style mock tools.
- State and history use SQLite tools.
- Low confidence produces a clarification question instead of a guess.

Tool calls are not hidden from persistence: every call is logged to `tool_runs`, and the plan plus decisions are logged to `agent_trace`.

## Chat Flow

The main flow is:

1. Agent asks for name, WhatsApp number, timezone, teams, athletes, sports/leagues, digest schedule, and WhatsApp consent.
2. User provides free text.
3. Entity extraction identifies known fields and sports entities.
4. Agent asks clarification for ambiguous entities, such as India Cricket.
5. Agent shows extracted preferences and asks whether to save them.
6. Agent plans event lookup tools and generates a digest preview.
7. Agent asks user to approve before sending.
8. Only after consent and approval does the mock WhatsApp sender run.
9. Agent saves digest history and activation state.

The app includes a sample input button matching the prototype:

`I am Mansoor. I follow the Lakers, Real Madrid, San Francisco 49ers, India cricket, Novak Djokovic and Max Verstappen. Send my digest every Friday morning to my WhatsApp.`

## Entity Extraction

The extractor is deterministic for the demo and modular for later LLM replacement. It supports at least:

- Los Angeles Lakers
- Real Madrid
- San Francisco 49ers
- India Cricket, with clarification for men's team, women's team, or both
- Novak Djokovic
- Max Verstappen

It returns teams, athletes, sports, ambiguous entities, schedule text, timezone if present, phone number if present, consent if present, and confidence scores.

## Digest Behavior

Each digest event includes:

- Sport icon
- Team or athlete
- Event name
- Opponent when applicable
- Date
- Time converted or labeled in the user's timezone
- League or tournament
- Source link
- Confidence indicator
- Mock/incomplete marker when applicable

The agent never fabricates uncertain event data. If a tool cannot find an event after retry and fallback, the entity appears in an unresolved section.

## State Management

Use SQLite with these tables:

- `users`
- `preferences`
- `sports_entities`
- `digest_history`
- `tool_runs`
- `agent_trace`

Stored data includes user profile, normalized entities, digest schedule, WhatsApp consent, generated digest payloads, approval status, tool outputs, errors, and trace records.

The database defaults to `fanpulse.db` in the repository root unless `FANPULSE_DB_PATH` is set.

## Error Recovery

Each API-like tool call retries once on failure. If the primary mock/API path fails, the agent uses the configured fallback:

- Team lookup fallback can try normalization or web search.
- Soccer lookup fallback can try API-Football-style lookup.
- Athlete lookup fallback uses web-search-style results.
- WhatsApp send failure saves an unsent digest and shows a friendly message.

All failures are logged in both `tool_runs` and `agent_trace`. The UI shows a friendly user-facing message while debug details stay inside the expander.

## Weekly Job

`weekly_digest_job.py` loads enrolled users from SQLite and, for each user:

1. Reconstructs the saved profile and preferences.
2. Runs the digest agent in scheduled mode.
3. Generates a new digest.
4. Sends WhatsApp only if consent exists.
5. Saves digest history.
6. Logs trace and tool runs.

Streamlit includes a manual "Run Weekly Digest Now" button for local demo, but background scheduling is left to cron or another external scheduler.

## Environment Variables

Add `.env.example` with:

- `THESPORTSDB_API_KEY=`
- `APIFOOTBALL_API_KEY=`
- `SERPAPI_API_KEY=`
- `TWILIO_ACCOUNT_SID=`
- `TWILIO_AUTH_TOKEN=`
- `TWILIO_WHATSAPP_FROM=`
- `FANPULSE_DB_PATH=fanpulse.db`

Missing provider keys keep the app in mock mode. Mock mode is clearly labeled in trace entries and tool outputs.

## Testing And Verification

Minimum verification:

- Import all package modules successfully.
- Run unit tests or a lightweight script for entity extraction, planner/tool flow, digest generation, and SQLite initialization.
- Launch Streamlit locally and verify the app starts.
- Exercise the sample onboarding path through preference confirmation, digest preview, approval, and mock WhatsApp send.
- Confirm database tables are created and trace/tool records are persisted.

## Scope Boundaries

This build does not need real API calls, real MCP server integration, or real Twilio delivery. It must make those later additions straightforward by preserving stable tool names, structured tool outputs, and provider separation.

