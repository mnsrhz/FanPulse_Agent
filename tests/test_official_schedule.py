from fanpulse_agent.agent import FanPulseAgent
from fanpulse_agent.database import FanPulseDB
from fanpulse_agent.models import Event, SportsEntity, ToolResult, UserProfile
from fanpulse_agent.tools import (
    discover_official_schedule_sources,
    extract_official_schedule_events,
    validate_official_schedule_events,
)


def _trusted_future_source():
    return {
        "title": "Los Angeles Lakers Schedule",
        "link": "https://www.nba.com/lakers/schedule",
        "snippet": "Los Angeles Lakers vs Golden State Warriors on June 19, 2999 at 7:30 PM.",
        "date": "2999-06-19",
    }


def test_trusted_future_schedule_result_becomes_event(monkeypatch):
    class FakeSerpAPIClient:
        last_errors = None

        def search(self, query):
            assert "Los Angeles Lakers" in query
            return [_trusted_future_source()]

    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_SERPAPI", raising=False)
    monkeypatch.setattr("fanpulse_agent.tools.SerpAPIClient", lambda: FakeSerpAPIClient())

    sources = discover_official_schedule_sources(
        "Los Angeles Lakers", "basketball", "team"
    )
    events = extract_official_schedule_events(
        "Los Angeles Lakers", "basketball", sources.data["sources"]
    )
    validated = validate_official_schedule_events(events.data["events"])

    assert sources.success is True
    assert sources.data["sources"][0]["domain"] == "nba.com"
    assert events.success is True
    event = events.data["events"][0]
    assert event.title == "Los Angeles Lakers vs Golden State Warriors"
    assert event.start_time == "2999-06-19"
    assert event.source_url == "https://www.nba.com/lakers/schedule"
    assert event.metadata["provider"] == "official-schedule"
    assert validated.success is True


def test_untrusted_schedule_result_is_ignored(monkeypatch):
    class FakeSerpAPIClient:
        last_errors = None

        def search(self, query):
            return [
                {
                    "title": "Random blog Lakers schedule",
                    "link": "https://random-blog.example/lakers",
                    "snippet": "Lakers play Warriors on June 19, 2999.",
                    "date": "2999-06-19",
                }
            ]

    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_SERPAPI", raising=False)
    monkeypatch.setattr("fanpulse_agent.tools.SerpAPIClient", lambda: FakeSerpAPIClient())

    sources = discover_official_schedule_sources(
        "Los Angeles Lakers", "basketball", "team"
    )

    assert sources.success is False
    assert sources.data["sources"] == []


def test_past_schedule_result_is_not_validated():
    sources = [
        {
            "title": "Los Angeles Lakers Schedule",
            "link": "https://www.nba.com/lakers/schedule",
            "snippet": "Los Angeles Lakers vs Warriors on June 19, 2020.",
            "date": "2020-06-19",
            "domain": "nba.com",
        }
    ]

    events = extract_official_schedule_events("Los Angeles Lakers", "basketball", sources)
    validated = validate_official_schedule_events(events.data["events"])

    assert events.success is False
    assert validated.success is False
    assert validated.data["events"] == []


def test_espn_page_text_becomes_future_event():
    sources = [
        {
            "title": "Los Angeles Lakers Schedule",
            "link": "https://www.espn.com/nba/team/schedule/_/name/lal/los-angeles-lakers",
            "snippet": "ESPN has the full schedule.",
            "date": None,
            "domain": "espn.com",
            "page_text": (
                '{"date":{"date":"2999-10-21T02:00Z"},"opponent":{'
                '"displayName":"Golden State Warriors"},"homeAwaySymbol":"vs",'
                '"time":{"time":"2999-10-21T02:00Z","link":"https://www.espn.com/nba/game/_/gameId/1"}}'
            ),
        }
    ]

    events = extract_official_schedule_events("Los Angeles Lakers", "basketball", sources)

    assert events.success is True
    event = events.data["events"][0]
    assert event.title == "Los Angeles Lakers vs Golden State Warriors"
    assert event.start_time == "2999-10-21T02:00Z"
    assert event.source_url == "https://www.espn.com/nba/game/_/gameId/1"
    assert event.metadata["source_parser"] == "espn-page"


def test_extract_fetches_trusted_page_when_snippet_has_no_date(monkeypatch):
    class FakeResponse:
        text = (
            '{"date":{"date":"2999-11-01T01:30Z"},"opponent":{'
            '"displayName":"Oklahoma City Thunder"},"homeAwaySymbol":"@",'
            '"time":{"time":"2999-11-01T01:30Z","link":"/nba/game/_/gameId/2"}}'
        )

        def raise_for_status(self):
            return None

    def fake_get(url, headers, timeout):
        assert url == "https://www.espn.com/nba/team/schedule/_/name/lal/los-angeles-lakers"
        assert timeout == 8
        return FakeResponse()

    monkeypatch.setattr("fanpulse_agent.tools.requests.get", fake_get)
    sources = [
        {
            "title": "Los Angeles Lakers Schedule",
            "link": "https://www.espn.com/nba/team/schedule/_/name/lal/los-angeles-lakers",
            "snippet": "ESPN has the full schedule.",
            "date": None,
            "domain": "espn.com",
        }
    ]

    events = extract_official_schedule_events("Los Angeles Lakers", "basketball", sources)

    assert events.success is True
    event = events.data["events"][0]
    assert event.title == "Los Angeles Lakers at Oklahoma City Thunder"
    assert event.source_url == "https://www.espn.com/nba/game/_/gameId/2"


def test_espn_soccer_fixture_page_text_becomes_future_event():
    sources = [
        {
            "title": "Arsenal Fixtures",
            "link": "https://www.espn.com/soccer/team/fixtures/_/id/359/arsenal",
            "snippet": "ESPN has the full Arsenal schedule.",
            "date": None,
            "domain": "espn.com",
            "page_text": (
                '"events":[{"id":"401875219","competitors":[{'
                '"displayName":"Arsenal","isHome":true},{"displayName":"Manchester City",'
                '"isHome":false}],"date":"2999-08-16T14:00Z","tbd":false,'
                '"completed":false,"link":"/soccer/match/_/gameId/401875219/manchester-city-arsenal"}]'
            ),
        }
    ]

    events = extract_official_schedule_events("Arsenal", "soccer", sources)

    assert events.success is True
    event = events.data["events"][0]
    assert event.title == "Arsenal vs Manchester City"
    assert event.start_time == "2999-08-16T14:00Z"
    assert event.source_url == "https://www.espn.com/soccer/match/_/gameId/401875219/manchester-city-arsenal"
    assert event.metadata["source_parser"] == "espn-soccer-page"


def test_formula1_known_source_does_not_require_serpapi(monkeypatch):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)

    sources = discover_official_schedule_sources("Max Verstappen", "formula 1", "athlete")

    assert sources.success is True
    assert sources.data["sources"][0]["domain"] == "formula1.com"
    assert "/en/racing/" in sources.data["sources"][0]["link"]


def test_formula1_page_text_becomes_future_race():
    sources = [
        {
            "title": "F1 Schedule 2999",
            "link": "https://www.formula1.com/en/racing/2999",
            "snippet": "Official Formula 1 race calendar.",
            "date": None,
            "domain": "formula1.com",
            "page_text": (
                '<a class="group/schedule-card" href="/en/racing/2999/austria">'
                '<span class="typography-module_body-2-xs-bold__M03Ei upper">ROUND 8</span>'
                '<span class="typography-module_display-xl-bold__Gyl5W group-hover/schedule-card:underline">Austria</span>'
                '<span class="typography-module_technical-m-regular__zphCD grow">26 - 28 JUN</span></a>'
            ),
        }
    ]

    events = extract_official_schedule_events("Formula 1", "formula 1", sources)

    assert events.success is True
    event = events.data["events"][0]
    assert event.title == "Formula 1: Austria Grand Prix"
    assert event.start_time == "2999-06-26"
    assert event.source_url == "https://www.formula1.com/en/racing/2999/austria"
    assert event.metadata["source_parser"] == "formula1-page"


def test_formula1_source_without_page_text_uses_cached_official_events():
    sources = [
        {
            "title": "F1 Schedule 2026",
            "link": "https://www.formula1.com/en/racing/2026",
            "snippet": "Official Formula 1 race calendar.",
            "date": None,
            "domain": "formula1.com",
        }
    ]

    events = extract_official_schedule_events("Max Verstappen", "formula 1", sources)

    assert events.success is True
    event = events.data["events"][0]
    assert event.title == "Formula 1: Austria Grand Prix"
    assert event.source_url == "https://www.formula1.com/en/racing/2026/austria"
    assert event.metadata["source_parser"] == "formula1-cached-official"
    assert event.mock is False


def test_extract_uses_curl_fallback_when_requests_fetch_fails(monkeypatch):
    class FailedResponse:
        def raise_for_status(self):
            raise RuntimeError("blocked")

    class FakeCompleted:
        returncode = 0
        stdout = (
            '<a class="group/schedule-card" href="/en/racing/2999/great-britain">'
            '<span class="typography-module_body-2-xs-bold__M03Ei upper">ROUND 9</span>'
            '<span class="typography-module_display-xl-bold__Gyl5W group-hover/schedule-card:underline">Great Britain</span>'
            '<span class="typography-module_technical-m-regular__zphCD grow">03 - 05 JUL</span></a>'
        )

    monkeypatch.setattr(
        "fanpulse_agent.tools.requests.get",
        lambda *args, **kwargs: FailedResponse(),
    )
    monkeypatch.setattr(
        "fanpulse_agent.tools.subprocess.run",
        lambda *args, **kwargs: FakeCompleted(),
    )
    sources = [
        {
            "title": "F1 Schedule 2999",
            "link": "https://www.formula1.com/en/racing/2999",
            "snippet": "Official Formula 1 race calendar.",
            "date": None,
            "domain": "formula1.com",
        }
    ]

    events = extract_official_schedule_events("Formula 1", "formula 1", sources)

    assert events.success is True
    assert events.data["events"][0].title == "Formula 1: Great Britain Grand Prix"


def test_event_without_source_url_is_not_validated():
    event = Event(
        title="Los Angeles Lakers vs Golden State Warriors",
        event_type="schedule",
        start_time="2999-06-19",
        source_url=None,
    )

    validated = validate_official_schedule_events([event])

    assert validated.success is False
    assert validated.data["events"] == []


def test_agent_uses_official_schedule_before_basketball_api(tmp_path, monkeypatch):
    import fanpulse_agent.agent as agent_module

    calls = []

    def fake_discover(entity_name, sport, entity_type):
        calls.append(("official", entity_name, sport, entity_type))
        return ToolResult(
            "official-schedule.discover_sources",
            True,
            {"sources": [_trusted_future_source() | {"domain": "nba.com"}]},
            "https://serpapi.com/search-api",
            None,
            0.85,
            False,
        )

    monkeypatch.setattr(agent_module, "discover_official_schedule_sources", fake_discover)

    agent = FanPulseAgent(FanPulseDB(str(tmp_path / "agent.db")))
    profile = UserProfile(
        name="Mansoor",
        name_provided=True,
        timezone_provided=True,
        teams=[SportsEntity(name="Los Angeles Lakers", entity_type="team", sport="basketball")],
    )

    events, unresolved = agent._collect_events(profile)

    assert unresolved == []
    assert events[0].metadata["provider"] == "official-schedule"
    assert calls == [("official", "Los Angeles Lakers", "basketball", "team")]


def test_agent_marks_unresolved_when_official_and_fallbacks_fail(tmp_path, monkeypatch):
    import fanpulse_agent.agent as agent_module

    def fail_discover(entity_name, sport, entity_type):
        return ToolResult(
            "official-schedule.discover_sources",
            False,
            {"sources": []},
            "https://serpapi.com/search-api",
            "no trusted source",
            0.2,
            False,
        )

    def fail_team_events(canonical_name):
        return []

    monkeypatch.setattr(agent_module, "discover_official_schedule_sources", fail_discover)
    monkeypatch.setattr(FanPulseAgent, "_collect_sportsdb_team_events", lambda self, name: fail_team_events(name))
    monkeypatch.setattr(FanPulseAgent, "_web_fallback_events", lambda self, name: [])

    agent = FanPulseAgent(FanPulseDB(str(tmp_path / "agent.db")))
    profile = UserProfile(
        name="Mansoor",
        name_provided=True,
        timezone_provided=True,
        teams=[SportsEntity(name="Los Angeles Lakers", entity_type="team", sport="basketball")],
    )

    events, unresolved = agent._collect_events(profile)

    assert events == []
    assert unresolved == ["Los Angeles Lakers"]


def test_agent_keeps_only_immediate_next_formula1_event_for_sport_profile(tmp_path):
    agent = FanPulseAgent(FanPulseDB(str(tmp_path / "agent.db")))
    profile = UserProfile(
        name="Mansoor",
        name_provided=True,
        timezone_provided=True,
        sports=["formula 1"],
    )

    events, unresolved = agent._collect_events(profile)

    assert unresolved == []
    assert len(events) == 1
    assert events[0].title == "Formula 1: Austria Grand Prix"
    assert events[0].source_url == "https://www.formula1.com/en/racing/2026/austria"


def test_agent_collects_official_events_for_formula1_sport_only_profile(tmp_path):
    agent = FanPulseAgent(FanPulseDB(str(tmp_path / "agent.db")))
    profile = UserProfile(
        name="Mansoor",
        name_provided=True,
        timezone_provided=True,
        sports=["formula 1"],
    )

    events, unresolved = agent._collect_events(profile)

    assert unresolved == []
    assert events
    assert events[0].metadata["provider"] == "official-schedule"
    assert events[0].metadata["source_parser"] == "formula1-cached-official"
