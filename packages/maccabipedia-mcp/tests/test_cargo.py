import json
import responses

WIKI_URL = "https://test.wiki.co.il"
API_URL = f"{WIKI_URL}/api.php"


@responses.activate
def test_list_cargo_tables(client):
    responses.get(
        API_URL,
        json={"cargotables": ["Football_Games", "Basketball_Games"]},
    )
    result = client.list_cargo_tables()
    assert result == ["Football_Games", "Basketball_Games"]


@responses.activate
def test_describe_cargo_table(client):
    responses.get(
        API_URL,
        json={"cargofields": {"Date": "Date", "Opponent": "String", "ResultMaccabi": "Integer"}},
    )
    result = client.describe_cargo_table("Football_Games")
    assert result == [
        {"name": "Date", "type": "Date"},
        {"name": "Opponent", "type": "String"},
        {"name": "ResultMaccabi", "type": "Integer"},
    ]


@responses.activate
def test_query_cargo(client):
    cargo_response = {
        "cargoquery": [
            {"title": {"_pageName": "Game1", "Date": "2025-01-01"}},
            {"title": {"_pageName": "Game2", "Date": "2025-01-02"}},
        ]
    }
    responses.get(API_URL, json=cargo_response)
    result = client.query_cargo(tables="Football_Games", fields="_pageName,Date")
    assert result == [
        {"_pageName": "Game1", "Date": "2025-01-01"},
        {"_pageName": "Game2", "Date": "2025-01-02"},
    ]


@responses.activate
def test_query_cargo_with_all_params(client):
    responses.get(API_URL, json={"cargoquery": []})
    client.query_cargo(
        tables="Football_Games",
        fields="_pageName",
        where="Date='2025-01-01'",
        join_on="",
        group_by="Season",
        having="COUNT(*)>1",
        order_by="Date ASC",
        limit=10,
        offset=5,
    )
    params = responses.calls[0].request.params
    assert params["tables"] == "Football_Games"
    assert params["fields"] == "_pageName=pageName"
    assert params["where"] == "Date='2025-01-01'"
    assert params["group_by"] == "Season"
    assert params["having"] == "COUNT(*)>1"
    assert params["order_by"] == "Date ASC"
    assert params["limit"] == "10"
    assert params["offset"] == "5"


from maccabipedia_mcp.wiki_client import WikiClient


def test_fix_cargo_field_aliases_bare_underscore():
    assert WikiClient._fix_cargo_field_aliases("_pageName") == "_pageName=pageName"


def test_fix_cargo_field_aliases_qualified():
    assert WikiClient._fix_cargo_field_aliases("Table._pageName") == "Table._pageName=pageName"


def test_fix_cargo_field_aliases_explicit_alias_left_alone():
    assert WikiClient._fix_cargo_field_aliases("_pageName=MyName") == "_pageName=MyName"


def test_fix_cargo_field_aliases_mixed():
    result = WikiClient._fix_cargo_field_aliases("_pageName, Date, Table._foo")
    assert result == "_pageName=pageName,Date,Table._foo=foo"


def test_fix_cargo_field_aliases_no_underscores():
    assert WikiClient._fix_cargo_field_aliases("Date,Opponent") == "Date,Opponent"


@responses.activate
def test_query_cargo_html_error(client):
    responses.get(
        API_URL,
        body="<html>Internal Server Error</html>",
        content_type="text/html",
    )
    result = client.query_cargo(tables="Football_Games", fields="_pageName")
    assert result["error"] is True
    assert "non-JSON" in result["message"]


@responses.activate
def test_describe_cargo_table_unknown_table_surfaces_api_error(client):
    responses.get(
        API_URL,
        json={"error": {"code": "db_error", "info": "Table Games not found."}},
    )
    result = client.describe_cargo_table("Games")
    assert result == {
        "error": True,
        "code": "db_error",
        "message": "Table Games not found.",
    }


@responses.activate
def test_query_cargo_unknown_table_surfaces_api_error(client):
    responses.get(
        API_URL,
        json={"error": {"code": "db_error", "info": "Table Games not found."}},
    )
    result = client.query_cargo(tables="Games", fields="_pageName")
    assert result == {
        "error": True,
        "code": "db_error",
        "message": "Table Games not found.",
    }
