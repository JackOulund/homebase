import json

import pytest

from tests.test_auth_flow import MCP_HEADERS, sign_in


@pytest.fixture
def access_token(client) -> str:
    return sign_in(client)["access_token"]


def send(client, access_token: str, method: str, params: dict) -> dict:
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        headers={**MCP_HEADERS, "Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200, response.text
    return response.json()["result"]


def call_tool(
    client, access_token: str, name: str, arguments: dict | None = None
) -> dict:
    return send(
        client, access_token, "tools/call", {"name": name, "arguments": arguments or {}}
    )


def payload(tool_result: dict) -> dict:
    assert not tool_result.get("isError"), tool_result
    if tool_result.get("structuredContent") is not None:
        return tool_result["structuredContent"]
    return json.loads(tool_result["content"][0]["text"])


def test_task_tools_are_offered_with_descriptions(client, access_token):
    tools = {
        tool["name"]: tool
        for tool in send(client, access_token, "tools/list", {})["tools"]
    }

    assert {"add_task", "list_tasks"} <= tools.keys()
    assert tools["add_task"]["description"]
    assert tools["list_tasks"]["description"]


def test_added_recurring_task_comes_back_with_its_details(client, access_token):
    task = payload(
        call_tool(
            client,
            access_token,
            "add_task",
            {
                "name": "Vacuum the living room",
                "estimated_minutes": 20,
                "interval_days": 7,
                "room": "living room",
                "notes": "Move the sofa",
            },
        )
    )

    assert task["id"] > 0
    assert task["name"] == "Vacuum the living room"
    assert task["estimated_minutes"] == 20
    assert task["interval_days"] == 7
    assert task["room"] == "living room"
    assert task["notes"] == "Move the sofa"
    assert task["last_done_at"] is None
    assert task["created_at"]


def test_task_can_be_captured_with_only_a_name(client, access_token):
    task = payload(
        call_tool(client, access_token, "add_task", {"name": "Fix dripping tap"})
    )

    assert task["name"] == "Fix dripping tap"
    assert task["estimated_minutes"] is None
    assert task["interval_days"] is None
    assert task["room"] is None
    assert task["notes"] is None


def test_name_is_trimmed(client, access_token):
    task = payload(
        call_tool(client, access_token, "add_task", {"name": "  Water plants  "})
    )

    assert task["name"] == "Water plants"


def test_listing_returns_every_added_task_in_order(client, access_token):
    call_tool(client, access_token, "add_task", {"name": "Vacuum", "interval_days": 7})
    call_tool(client, access_token, "add_task", {"name": "Fix dripping tap"})

    listing = payload(call_tool(client, access_token, "list_tasks"))

    assert [task["name"] for task in listing["tasks"]] == ["Vacuum", "Fix dripping tap"]
    assert listing["tasks"][0]["interval_days"] == 7


def test_listing_is_empty_before_anything_is_added(client, access_token):
    assert payload(call_tool(client, access_token, "list_tasks")) == {"tasks": []}


@pytest.mark.parametrize(
    "arguments",
    [
        {"name": "   "},
        {"name": "Vacuum", "estimated_minutes": 0},
        {"name": "Vacuum", "estimated_minutes": -5},
        {"name": "Vacuum", "interval_days": 0},
    ],
)
def test_invalid_task_is_refused_and_not_stored(client, access_token, arguments):
    result = call_tool(client, access_token, "add_task", arguments)

    assert result["isError"]
    assert payload(call_tool(client, access_token, "list_tasks")) == {"tasks": []}


def test_tasks_survive_a_restart(client, access_token, settings):
    from fastapi.testclient import TestClient

    from homebase.app import create_app
    from tests.conftest import PUBLIC_URL

    call_tool(client, access_token, "add_task", {"name": "Descale kettle"})

    with TestClient(create_app(settings), base_url=PUBLIC_URL) as restarted:
        listing = payload(call_tool(restarted, access_token, "list_tasks"))

    assert [task["name"] for task in listing["tasks"]] == ["Descale kettle"]
