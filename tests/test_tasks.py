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


def add(client, access_token, **arguments) -> dict:
    return payload(call_tool(client, access_token, "add_task", arguments))


def open_task_names(client, access_token) -> list[str]:
    listing = payload(call_tool(client, access_token, "list_tasks"))
    return [task["name"] for task in listing["tasks"]]


def test_completing_a_one_off_task_removes_it_from_the_list(client, access_token):
    tap = add(client, access_token, name="Fix dripping tap")
    add(client, access_token, name="Hang the mirror")

    done = payload(
        call_tool(client, access_token, "complete_task", {"task_id": tap["id"]})
    )

    assert done["task"]["last_done_at"] is not None
    assert open_task_names(client, access_token) == ["Hang the mirror"]


def test_completing_a_recurring_task_keeps_it_and_records_when(client, access_token):
    vacuum = add(client, access_token, name="Vacuum", interval_days=7)

    done = payload(
        call_tool(client, access_token, "complete_task", {"task_id": vacuum["id"]})
    )

    assert done["task"]["last_done_at"] is not None
    assert open_task_names(client, access_token) == ["Vacuum"]


def test_completion_reports_how_the_actual_time_compared(client, access_token):
    vacuum = add(
        client, access_token, name="Vacuum", interval_days=7, estimated_minutes=20
    )

    done = payload(
        call_tool(
            client,
            access_token,
            "complete_task",
            {"task_id": vacuum["id"], "actual_minutes": 35},
        )
    )

    assert done["actual_minutes"] == 35
    assert done["times_done"] == 1
    assert done["average_actual_minutes"] == 35


def test_average_actual_time_builds_up_over_completions(client, access_token):
    vacuum = add(client, access_token, name="Vacuum", interval_days=7)
    for minutes in (20, 30):
        done = payload(
            call_tool(
                client,
                access_token,
                "complete_task",
                {"task_id": vacuum["id"], "actual_minutes": minutes},
            )
        )

    assert done["times_done"] == 2
    assert done["average_actual_minutes"] == 25


def test_completing_an_unknown_task_is_an_error(client, access_token):
    assert call_tool(client, access_token, "complete_task", {"task_id": 999})["isError"]


def test_completing_with_non_positive_minutes_is_an_error(client, access_token):
    vacuum = add(client, access_token, name="Vacuum", interval_days=7)

    result = call_tool(
        client,
        access_token,
        "complete_task",
        {"task_id": vacuum["id"], "actual_minutes": 0},
    )

    assert result["isError"]


def test_update_changes_only_the_given_fields(client, access_token):
    vacuum = add(
        client, access_token, name="Vacuum", interval_days=7, room="living room"
    )

    updated = payload(
        call_tool(
            client,
            access_token,
            "update_task",
            {"task_id": vacuum["id"], "estimated_minutes": 25, "interval_days": 14},
        )
    )

    assert updated["name"] == "Vacuum"
    assert updated["room"] == "living room"
    assert updated["estimated_minutes"] == 25
    assert updated["interval_days"] == 14


def test_update_can_rename_and_rejects_a_blank_name(client, access_token):
    vacuum = add(client, access_token, name="Vacuum")

    renamed = payload(
        call_tool(
            client,
            access_token,
            "update_task",
            {"task_id": vacuum["id"], "name": "Vacuum everywhere"},
        )
    )
    blank = call_tool(
        client, access_token, "update_task", {"task_id": vacuum["id"], "name": " "}
    )

    assert renamed["name"] == "Vacuum everywhere"
    assert blank["isError"]


def test_update_of_an_unknown_task_is_an_error(client, access_token):
    result = call_tool(
        client, access_token, "update_task", {"task_id": 999, "name": "Nope"}
    )

    assert result["isError"]


def test_removed_task_disappears_and_cannot_be_completed(client, access_token):
    vacuum = add(client, access_token, name="Vacuum", interval_days=7)

    removed = payload(
        call_tool(client, access_token, "remove_task", {"task_id": vacuum["id"]})
    )

    assert removed["removed"]["name"] == "Vacuum"
    assert open_task_names(client, access_token) == []
    assert call_tool(client, access_token, "complete_task", {"task_id": vacuum["id"]})[
        "isError"
    ]


def test_update_trims_room_and_refuses_when_nothing_is_given(client, access_token):
    vacuum = add(client, access_token, name="Vacuum")

    updated = payload(
        call_tool(
            client,
            access_token,
            "update_task",
            {"task_id": vacuum["id"], "room": "  hall  "},
        )
    )
    nothing = call_tool(
        client, access_token, "update_task", {"task_id": vacuum["id"], "notes": "  "}
    )

    assert updated["room"] == "hall"
    assert nothing["isError"]


def suggestions(client, access_token, **arguments) -> dict:
    return payload(call_tool(client, access_token, "suggest_tasks", arguments))


def test_new_tasks_are_due_immediately(client, access_token):
    add(client, access_token, name="Vacuum", interval_days=7, estimated_minutes=20)

    result = suggestions(client, access_token, minutes=30)

    assert [task["name"] for task in result["suggestions"]] == ["Vacuum"]
    assert result["minutes_planned"] == 20


def test_recurring_task_just_completed_is_not_suggested(client, access_token):
    vacuum = add(client, access_token, name="Vacuum", interval_days=7)
    call_tool(client, access_token, "complete_task", {"task_id": vacuum["id"]})

    assert suggestions(client, access_token, minutes=30)["suggestions"] == []


def test_task_longer_than_the_available_time_is_mentioned_not_picked(
    client, access_token
):
    add(client, access_token, name="Clean windows", estimated_minutes=60)

    result = suggestions(client, access_token, minutes=30)

    assert result["suggestions"] == []
    assert result["due_but_too_long"][0]["name"] == "Clean windows"
    assert result["due_but_too_long"][0]["minutes"] == 60


def test_at_most_three_tasks_are_suggested(client, access_token):
    for number in range(5):
        add(client, access_token, name=f"Job {number}", estimated_minutes=5)

    assert len(suggestions(client, access_token, minutes=120)["suggestions"]) == 3


def test_suggestions_can_be_limited_to_a_room(client, access_token):
    add(client, access_token, name="Wipe hob", room="Kitchen")
    add(client, access_token, name="Scrub bath", room="Bathroom")

    result = suggestions(client, access_token, minutes=60, room=" kitchen")

    assert [task["name"] for task in result["suggestions"]] == ["Wipe hob"]


@pytest.mark.parametrize("minutes", [0, -5])
def test_suggesting_with_non_positive_minutes_is_an_error(
    client, access_token, minutes
):
    assert call_tool(client, access_token, "suggest_tasks", {"minutes": minutes})[
        "isError"
    ]


def complete(client, access_token, task_id: int, actual_minutes: int | None = None):
    arguments = {"task_id": task_id, "actual_minutes": actual_minutes}
    return payload(call_tool(client, access_token, "complete_task", arguments))


def time_history(client, access_token) -> list[dict]:
    return payload(call_tool(client, access_token, "get_time_history"))["history"]


def test_history_is_empty_before_any_timed_completion(client, access_token):
    task = add(client, access_token, name="Vacuum", interval_days=7)
    complete(client, access_token, task["id"])

    assert time_history(client, access_token) == []


def test_history_averages_the_timed_completions_per_task(client, access_token):
    vacuum = add(
        client,
        access_token,
        name="Vacuum",
        interval_days=7,
        room="hall",
        estimated_minutes=20,
    )
    for minutes in (20, 31, None):
        complete(client, access_token, vacuum["id"], minutes)

    assert time_history(client, access_token) == [
        {
            "id": vacuum["id"],
            "name": "Vacuum",
            "room": "hall",
            "estimated_minutes": 20,
            "times_done": 2,
            "average_actual_minutes": 26,
        }
    ]


def test_history_is_ordered_by_task_id_and_skips_removed_tasks(client, access_token):
    first = add(client, access_token, name="Vacuum", interval_days=7)
    second = add(client, access_token, name="Mop", interval_days=7)
    removed = add(client, access_token, name="Dust", interval_days=7)
    for task in (second, removed, first):
        complete(client, access_token, task["id"], 10)
    call_tool(client, access_token, "remove_task", {"task_id": removed["id"]})

    names = [entry["name"] for entry in time_history(client, access_token)]

    assert names == ["Vacuum", "Mop"]
