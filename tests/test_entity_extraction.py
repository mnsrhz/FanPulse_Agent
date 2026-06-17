import pytest

from fanpulse_agent.models import SportsEntity, ToolResult
from fanpulse_agent.llm_reasoning import ReasonedUserFacts
from fanpulse_agent.entity_extraction import extract_profile_from_text


def test_models_serialize_to_dict():
    entity = SportsEntity(name="Los Angeles Lakers", entity_type="team", sport="basketball")
    result = ToolResult(
        tool_name="sportsdb.search_team",
        success=True,
        data={"name": entity.name},
        source_url="https://www.thesportsdb.com/",
        error=None,
        confidence=0.95,
        mock=True,
    )
    assert entity.to_dict()["sport"] == "basketball"
    assert result.to_dict()["tool_name"] == "sportsdb.search_team"
    assert result.to_dict()["mock"] is True


def test_extracts_sample_onboarding_entities():
    text = (
        "I am Mansoor. I follow the Lakers, Real Madrid, India cricket, "
        "Novak Djokovic and Max Verstappen. Send my digest every Friday morning "
        "to +14155550123 on WhatsApp."
    )
    profile, ambiguous = extract_profile_from_text(text)
    assert profile.name == "Mansoor"
    assert profile.phone_number == "+14155550123"
    assert profile.digest_schedule == "Friday morning"
    assert profile.whatsapp_consent is True
    assert [team.name for team in profile.teams] == [
        "Los Angeles Lakers",
        "Real Madrid",
        "India Cricket",
    ]
    assert [athlete.name for athlete in profile.athletes] == [
        "Novak Djokovic",
        "Max Verstappen",
    ]
    assert set(profile.sports) >= {"basketball", "soccer", "cricket", "tennis", "formula 1"}
    assert ambiguous[0].name == "India Cricket"
    assert ambiguous[0].to_dict()["needs_clarification"] is True

    profile_data = profile.to_dict()
    assert profile_data["phone_number"] == "+14155550123"
    assert profile_data["digest_schedule"] == "Friday morning"
    assert profile_data["schedule_provided"] is True
    assert [team["name"] for team in profile_data["teams"]] == [
        "Los Angeles Lakers",
        "Real Madrid",
        "India Cricket",
    ]
    assert [athlete["name"] for athlete in profile_data["athletes"]] == [
        "Novak Djokovic",
        "Max Verstappen",
    ]
    assert set(profile_data["sports"]) >= {
        "basketball",
        "soccer",
        "cricket",
        "tennis",
        "formula 1",
    }


def test_extracts_49ers_as_american_football():
    profile, ambiguous = extract_profile_from_text("I am Alex. I follow the 49ers.")

    assert ambiguous == []
    assert [team.name for team in profile.teams] == ["San Francisco 49ers"]
    assert profile.sports == ["american football"]


def test_extracts_formula1_as_league_from_plain_sport_preference():
    profile, ambiguous = extract_profile_from_text("I follow Formula 1")

    assert ambiguous == []
    assert [league.name for league in profile.leagues] == ["Formula 1"]
    assert profile.leagues[0].sport == "formula 1"
    assert profile.sports == ["formula 1"]


def test_whatsapp_consent_is_false_for_explicit_refusal():
    refusal_samples = [
        "Do not send anything on WhatsApp",
        "Don't send updates on WhatsApp",
        "No WhatsApp please",
        "Do not send my digest over WhatsApp",
    ]

    for text in refusal_samples:
        profile, _ = extract_profile_from_text(text)

        assert profile.whatsapp_consent is False


def test_source_text_uses_matched_alias_from_user_input():
    profile, _ = extract_profile_from_text("I follow the Lakers")

    assert profile.teams[0].name == "Los Angeles Lakers"
    assert profile.teams[0].source_text == "Lakers"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Send it to +1 415-555-0123 on WhatsApp.", "+14155550123"),
        ("Send it to (415) 555-0123 on WhatsApp.", "+14155550123"),
        ("Send it to 415.555.0123 on WhatsApp.", "+14155550123"),
    ],
)
def test_extract_profile_accepts_common_phone_formats(text, expected):
    profile, _ = extract_profile_from_text(text)

    assert profile.phone_number == expected
    assert profile.whatsapp_consent is True


def test_extract_profile_tracks_missing_and_explicit_identity_fields():
    missing_profile, _ = extract_profile_from_text("I follow the Lakers.")
    explicit_profile, _ = extract_profile_from_text(
        "I'm Mansoor. I follow the Lakers. Use Pacific time."
    )

    assert missing_profile.name == "Fan"
    assert missing_profile.name_provided is False
    assert missing_profile.timezone == "America/Los_Angeles"
    assert missing_profile.timezone_provided is False
    assert explicit_profile.name == "Mansoor"
    assert explicit_profile.name_provided is True
    assert explicit_profile.timezone == "America/Los_Angeles"
    assert explicit_profile.timezone_provided is True


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Send updates every 1 hour.", "Every 1 hour"),
        ("Send updates hourly.", "Every 1 hour"),
        ("I want updates every 2 hours.", "Every 2 hours"),
        ("Send my digest daily.", "Daily"),
    ],
)
def test_extract_profile_understands_update_frequency(text, expected):
    profile, _ = extract_profile_from_text(text)

    assert profile.digest_schedule == expected
    assert profile.schedule_provided is True


@pytest.mark.parametrize(
    ("text", "expected_name", "expected_timezone"),
    [
        ("Mansoor, California", "Mansoor", "America/Los_Angeles"),
        ("My name's Mansoor and I'm in SF.", "Mansoor", "America/Los_Angeles"),
        ("This is Aisha. I am in New York.", "Aisha", "America/New_York"),
    ],
)
def test_extract_profile_understands_natural_identity_replies(
    text, expected_name, expected_timezone
):
    profile, _ = extract_profile_from_text(text)

    assert profile.name == expected_name
    assert profile.name_provided is True
    assert profile.timezone == expected_timezone
    assert profile.timezone_provided is True


def test_extract_profile_uses_llm_reasoned_facts(monkeypatch):
    monkeypatch.setattr(
        "fanpulse_agent.entity_extraction.reason_about_user_message",
        lambda text: ReasonedUserFacts(
            name="Mansoor",
            timezone="America/Los_Angeles",
            phone_number="+1 415 555 0123",
            whatsapp_consent=True,
            digest_schedule="Friday morning",
        ),
    )

    profile, _ = extract_profile_from_text("sure")

    assert profile.name == "Mansoor"
    assert profile.name_provided is True
    assert profile.timezone == "America/Los_Angeles"
    assert profile.timezone_provided is True
    assert profile.phone_number == "+14155550123"
    assert profile.whatsapp_consent is True
    assert profile.digest_schedule == "Friday morning"


def test_extract_profile_preserves_llm_identified_teams_outside_local_catalog(monkeypatch):
    monkeypatch.setattr(
        "fanpulse_agent.entity_extraction.reason_about_user_message",
        lambda text: ReasonedUserFacts(
            teams=[
                {"name": "Arsenal", "sport": "soccer", "league": "Premier League"},
                {"name": "Manchester United", "sport": "soccer", "league": "Premier League"},
            ],
            sports=["soccer"],
        ),
    )

    profile, ambiguous = extract_profile_from_text("I follow Arsenal and Manchester United")

    assert ambiguous == []
    assert [team.name for team in profile.teams] == ["Arsenal", "Manchester United"]
    assert [team.sport for team in profile.teams] == ["soccer", "soccer"]
    assert profile.teams[0].confidence == pytest.approx(0.72)
    assert profile.sports == ["soccer"]


def test_extract_profile_preserves_llm_identified_leagues(monkeypatch):
    monkeypatch.setattr(
        "fanpulse_agent.entity_extraction.reason_about_user_message",
        lambda text: ReasonedUserFacts(
            leagues=[
                {
                    "name": "English Premier League",
                    "sport": "soccer",
                    "league": "English Premier League",
                }
            ],
            sports=["soccer"],
        ),
    )

    profile, ambiguous = extract_profile_from_text("I follow the Premier League")

    assert ambiguous == []
    assert [league.name for league in profile.leagues] == ["English Premier League"]
    assert profile.leagues[0].entity_type == "league"
    assert profile.sports == ["soccer"]
