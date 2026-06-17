# Official Schedule Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make official/reliable schedule search the first event-discovery path before SportsDB, API-Football, API-SPORTS, or SerpAPI fallback.

**Architecture:** Add a local MCP-style official schedule tool layer that discovers trusted schedule sources from search results, extracts future events from trusted snippets/pages, and validates source URLs. The agent calls this layer before sport API fallbacks and marks unresolved when no confident future event is found.

**Tech Stack:** Python 3.9, pytest, existing `requests`/SerpAPI client, existing FanPulse `Event` and `ToolResult` models.

---

## File Structure

- Create `src/fanpulse_agent/official_schedule.py`: trusted-domain checks, source discovery, date extraction, and event normalization helpers.
- Modify `src/fanpulse_agent/tools.py`: expose `official-schedule.*` tool wrappers and registry entries.
- Modify `src/fanpulse_agent/agent.py`: call official schedule tools before sports API fallbacks for teams, athletes, and leagues.
- Modify `src/fanpulse_agent/agent_planner.py`: put official schedule tool names first in deterministic and LLM tool plans.
- Create `tests/test_official_schedule.py`: deterministic tests for trusted/untrusted/past event extraction and agent routing.

---

### Task 1: Official Schedule Tool Layer

- [ ] Write tests in `tests/test_official_schedule.py` proving:
  - trusted future search result becomes an event with source URL;
  - untrusted result is ignored;
  - past-dated result is ignored;
  - validation fails events without source URL.
- [ ] Run focused tests and verify they fail because tools do not exist.
- [ ] Implement `official_schedule.py` and wrappers in `tools.py`.
- [ ] Rerun focused tests and verify they pass.

### Task 2: Agent Source Priority

- [ ] Add tests proving the agent calls official schedule before API fallback and marks unresolved when official search plus fallback fail.
- [ ] Run focused tests and verify they fail on current provider-first routing.
- [ ] Update `agent.py` to try official schedule for each entity before existing provider logic.
- [ ] Rerun focused tests and verify they pass.

### Task 3: Planner And Verification

- [ ] Update `agent_planner.py` so `official-schedule.discover_sources`, `official-schedule.extract_events`, and `official-schedule.validate_events` appear before fallback providers.
- [ ] Run the official schedule tests.
- [ ] Run full deterministic test suite with live providers disabled.
- [ ] Run compile and Streamlit smoke.
- [ ] Restart Streamlit on port `8503`.
