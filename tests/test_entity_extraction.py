from fanpulse_agent.models import SportsEntity, ToolResult
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
