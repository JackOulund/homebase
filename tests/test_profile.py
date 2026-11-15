import pytest
from fastapi.testclient import TestClient

from homebase.app import create_app
from tests.conftest import PUBLIC_URL
from tests.test_auth_flow import sign_in
from tests.test_tasks import add, call_tool, payload, send


@pytest.fixture
def access_token(client) -> str:
    return sign_in(client)["access_token"]


def profile(client, access_token) -> dict:
    return payload(call_tool(client, access_token, "get_profile"))["profile"]


def set_entry(client, access_token, key: str, value: str) -> dict:
    return call_tool(
        client, access_token, "set_profile_entry", {"key": key, "value": value}
    )


def test_profile_tools_are_offered_with_descriptions(client, access_token):
    tools = {
        tool["name"]: tool
        for tool in send(client, access_token, "tools/list", {})["tools"]
    }

    expected = {
        "get_profile",
        "set_profile_entry",
        "remove_profile_entry",
        "get_time_history",
    }
    assert expected <= tools.keys()
    assert all(tools[name]["description"] for name in expected)


def test_profile_is_empty_at_first(client, access_token):
    assert profile(client, access_token) == {}


def test_setting_an_entry_returns_the_whole_profile_ordered_by_key(
    client, access_token
):
    set_entry(client, access_token, "rooms", "4")
    result = payload(set_entry(client, access_token, "floors", "2"))

    assert result == {"profile": {"floors": "2", "rooms": "4"}}
    assert list(profile(client, access_token)) == ["floors", "rooms"]


def test_key_and_value_are_trimmed_and_the_key_lowercased(client, access_token):
    set_entry(client, access_token, "  Size M2 ", "  95  ")

    assert profile(client, access_token) == {"size m2": "95"}


def test_setting_an_existing_key_replaces_its_value(client, access_token):
    set_entry(client, access_token, "garden", "small")
    set_entry(client, access_token, "GARDEN", "large")

    assert profile(client, access_token) == {"garden": "large"}


@pytest.mark.parametrize("key, value", [("  ", "x"), ("garden", "  ")])
def test_blank_key_or_value_is_an_error(client, access_token, key, value):
    assert set_entry(client, access_token, key, value)["isError"]
    assert profile(client, access_token) == {}


def test_removing_an_entry_returns_the_remaining_profile(client, access_token):
    set_entry(client, access_token, "garden", "large")
    set_entry(client, access_token, "rooms", "4")

    result = payload(
        call_tool(client, access_token, "remove_profile_entry", {"key": " Garden "})
    )

    assert result == {"profile": {"rooms": "4"}}


def test_removing_an_unknown_entry_is_an_error(client, access_token):
    result = call_tool(client, access_token, "remove_profile_entry", {"key": "nope"})

    assert result["isError"]


def test_updating_an_entry_moves_its_updated_at_forward(client, access_token, settings):
    import sqlalchemy as sa

    set_entry(client, access_token, "garden", "small")
    engine = sa.create_engine(settings.database_url)
    with engine.begin() as connection:
        connection.execute(
            sa.text("update profile_entries set updated_at = '2000-01-01'")
        )
    set_entry(client, access_token, "garden", "large")
    with engine.connect() as connection:
        newer = connection.scalar(
            sa.text("select updated_at > '2000-01-02' from profile_entries")
        )
    engine.dispose()

    assert newer


def test_profile_and_history_survive_a_restart(client, access_token, settings):
    vacuum = add(client, access_token, name="Vacuum", interval_days=7)
    call_tool(
        client,
        access_token,
        "complete_task",
        {"task_id": vacuum["id"], "actual_minutes": 25},
    )
    set_entry(client, access_token, "garden", "large")

    with TestClient(create_app(settings), base_url=PUBLIC_URL) as restarted:
        restarted_profile = payload(call_tool(restarted, access_token, "get_profile"))
        history = payload(call_tool(restarted, access_token, "get_time_history"))

    assert restarted_profile == {"profile": {"garden": "large"}}
    assert [entry["name"] for entry in history["history"]] == ["Vacuum"]
