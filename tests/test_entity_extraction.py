from fanpulse_agent.models import SportsEntity, ToolResult


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
