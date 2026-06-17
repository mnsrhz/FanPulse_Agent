# FanPulse Official Schedule Search Design

Date: 2026-06-17

## Goal

Change FanPulse event discovery so official or reliable public schedule pages are the primary source of truth. SportsDB, API-Football, API-SPORTS, and SerpAPI remain useful tools, but they are not treated as authoritative schedule dependencies.

The first implementation uses basic search and lightweight page extraction. Firecrawl or a dedicated crawler can be added later.

## Source Priority

For each team, athlete, league, or sport preference, the agent should prefer sources in this order:

1. Official team, league, competition, tournament, or athlete schedule pages.
2. Reliable public schedule pages such as NBA.com, ESPN, Formula1.com, ATP/WTA pages, team sites, or league sites.
3. Structured sports APIs as optional fallback tools.
4. Search-result snippets only as discovery or low-confidence fallback.

Every event in a digest must include a source URL. If a future event cannot be extracted confidently, the entity is marked unresolved and the user is asked to review it.

## Agentic Planning

The OpenAI model remains the planning brain. It should plan source discovery before provider fallback:

- Discover likely official/reliable schedule URLs for each entity.
- Fetch candidate pages or search-result snippets.
- Extract future event candidates.
- Validate that event dates are future dates and the source URL is present.
- Use sports APIs only when official/reliable page extraction fails.
- Mark unresolved when confidence is low.

The deterministic fallback should mirror this behavior for tests.

## Basic Search Tool Layer

Add MCP-style local tools:

- `official-schedule.discover_sources(entity_name, sport, entity_type)`
- `official-schedule.extract_events(entity_name, sport, sources)`
- `official-schedule.validate_events(events)`

The first version may use SerpAPI/Google search results for discovery, but extracted events should only be accepted when the URL domain is trusted or obviously official/reliable.

## Trusted Domains

Start with a small trusted-domain allowlist and keep it easy to extend:

- `nba.com`
- `espn.com`
- `formula1.com`
- `atptour.com`
- `wtatennis.com`
- `premierleague.com`
- `laliga.com`
- `realmadrid.com`
- `arsenal.com`
- `thefa.com`
- `icc-cricket.com`

The agent can still log untrusted candidates, but they should not become digest events without review.

## Event Extraction Rules

An accepted event must include:

- title
- future date or date/time
- source URL
- source domain
- sport
- entity name
- confidence
- provider/source label

If the page/search result does not expose a clear future date, the event is not accepted. The entity becomes unresolved unless another trusted source or structured fallback provides a future event with a source URL.

## Fallback Policy

Sports APIs are optional fallback tools:

- They may supply structured event data when official schedule extraction fails.
- Their event source URL must be preserved.
- Provider plan-limit errors or empty results should be logged and should not fabricate events.
- Mock data is only for demo/test mode and should remain clearly marked as mock.

## UI And WhatsApp Impact

The UI digest card and WhatsApp digest should show the source URL for every event. Unresolved entities should remain visible so the user can review missing or low-confidence preferences.

## Testing

Add deterministic tests for:

- trusted official schedule result is accepted as a future event;
- untrusted search result is ignored;
- past dated result is ignored;
- no confident future event marks the entity unresolved;
- APIs are called only after official/reliable search fails;
- every digest event includes a source URL;
- WhatsApp body includes source URL and event date/time.
