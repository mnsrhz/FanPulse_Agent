# FanPulse Multi-Provider Sports Tools Design

Date: 2026-06-17

## Goal

Extend FanPulse so the OpenAI planner can choose structured provider tools for basketball, Formula 1, and web-search fallback in addition to the existing soccer and SportsDB paths.

The implementation remains mock-safe and demo-safe: missing keys or provider plan limits must not break onboarding or digest generation. Live provider errors are preserved in tool results and trace logs so the app can explain what happened while still falling back to other sources.

## Provider Scope

Add three provider families:

- API-SPORTS Basketball for teams, leagues, and upcoming games.
- API-SPORTS Formula 1 for drivers and upcoming race context.
- SerpAPI for sports event and sports news fallback.

API-Football remains soccer-only. The new Basketball and Formula 1 clients should not be modeled as API-Football tools because API-SPORTS products have separate base URLs and endpoint shapes.

## Tool Names

Add stable tool names that can later move behind a real MCP server without changing the agent flow:

- `api-basketball.search_team`
- `api-basketball.get_team_games`
- `api-basketball.search_league`
- `api-basketball.get_league_games`
- `api-formula1.search_driver`
- `api-formula1.get_next_races`
- `api-formula1.get_driver_context`
- `serpapi.search_sports_events`
- `serpapi.search_sports_news`

Each tool returns the existing `ToolResult` shape with `success`, `data`, `source_url`, `error`, `confidence`, and `mock`.

## LLM Planning

The OpenAI planner remains the agent brain. It receives the profile summary and chooses the provider tools by sport and entity type:

- Soccer team or league: API-Football, then TheSportsDB, then SerpAPI.
- Basketball team or league: API-Basketball, then TheSportsDB, then SerpAPI.
- Formula 1 driver or team: API-Formula1, then SerpAPI.
- Tennis, cricket, unclear athletes, or provider misses: TheSportsDB when useful, then SerpAPI.

The deterministic fallback plan mirrors the same routing so tests do not depend on OpenAI availability.

## Normalized Events

All providers normalize into the existing `Event` model:

- `title`
- `event_type`
- `start_time`
- `display_time` with full date and year
- `sport_icon`
- `entity_name`
- `source_url`
- `metadata.provider`
- `metadata.league` or competition
- `metadata.mock`
- `metadata.confidence`

Provider-specific IDs remain in metadata, such as `game_id`, `race_id`, `driver_id`, or `serpapi_result_id`.

## Error Handling

Live API failures, plan-limit messages, quota errors, empty future schedules, and malformed payloads return `mock=False` with a meaningful `error`. The agent logs these results, then attempts the next fallback.

The user-facing digest should not show raw stack traces. Debug details stay in the trace/debug expander.

## MCP-Ready Boundary

This implementation uses local Python functions as MCP-style tools. The boundary should be explicit:

- Provider clients only perform HTTP calls and light payload extraction.
- Tool wrappers normalize provider payloads into FanPulse models.
- The agent only calls named tools and consumes `ToolResult`.

This lets the local tool layer be moved into a real MCP server later with minimal changes to the planner and Streamlit app.

## Environment Variables

Extend `.env.example`:

- `APISPORTS_BASKETBALL_API_KEY=`
- `FANPULSE_DISABLE_LIVE_APISPORTS_BASKETBALL=0`
- `APISPORTS_FORMULA1_API_KEY=`
- `FANPULSE_DISABLE_LIVE_APISPORTS_FORMULA1=0`
- `SERPAPI_API_KEY=`
- `FANPULSE_DISABLE_LIVE_SERPAPI=0`

If sport-specific API-SPORTS keys are missing, tools may optionally fall back to `APIFOOTBALL_API_KEY` only if live testing confirms the same key is valid across products. The code should not assume cross-product access without graceful failure.

## Testing

Add deterministic tests with fake clients:

- Basketball team search and game normalization.
- Formula 1 driver search and race normalization.
- SerpAPI event/news fallback normalization.
- Agent routes Lakers through Basketball before SportsDB.
- Agent routes Max Verstappen through Formula 1 before SerpAPI.
- Provider plan-limit errors stay visible as live, non-mock errors.
- Full suite passes with all live providers disabled.

Live smoke tests should print only success, mock status, event counts, and provider errors. They must never print API keys.
