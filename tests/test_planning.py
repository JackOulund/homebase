from datetime import UTC, datetime, timedelta

import pytest

from homebase.planning import plan, urgency

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


def days_ago(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat()


def task(
    id: int = 1,
    name: str = "Task",
    estimated_minutes: int | None = 10,
    interval_days: int | None = None,
    room: str | None = None,
    created_days_ago: float = 0,
    done_days_ago: float | None = None,
) -> dict:
    return {
        "id": id,
        "name": name,
        "notes": None,
        "room": room,
        "estimated_minutes": estimated_minutes,
        "interval_days": interval_days,
        "created_at": days_ago(created_days_ago),
        "last_done_at": None if done_days_ago is None else days_ago(done_days_ago),
    }


def suggested_ids(result: dict) -> list[int]:
    return [suggestion["id"] for suggestion in result["suggestions"]]


def test_recurring_task_urgency_is_time_since_done_over_interval():
    weekly = task(interval_days=7, created_days_ago=100, done_days_ago=14)

    assert urgency(weekly, NOW) == 2.0


def test_recurring_task_never_done_starts_at_one_and_grows_with_age():
    weekly = task(interval_days=7, created_days_ago=14)

    assert urgency(weekly, NOW) == 3.0


def test_one_off_task_starts_at_one_and_grows_over_thirty_days():
    repair = task(created_days_ago=15)

    assert urgency(repair, NOW) == 1.5


def test_task_just_done_is_not_suggested():
    result = plan([task(interval_days=7, done_days_ago=0)], 60, NOW)

    assert result["suggestions"] == []


def test_task_at_ninety_percent_of_its_interval_is_due():
    almost = task(id=1, interval_days=10, done_days_ago=9)
    not_yet = task(id=2, interval_days=10, done_days_ago=8.9)

    assert suggested_ids(plan([almost, not_yet], 60, NOW)) == [1]


def test_most_urgent_task_comes_first_and_ties_go_to_the_lower_id():
    tasks = [
        task(id=3, interval_days=7, done_days_ago=7),
        task(id=2, interval_days=7, done_days_ago=14),
        task(id=1, interval_days=7, done_days_ago=7),
    ]

    assert suggested_ids(plan(tasks, 60, NOW)) == [2, 1, 3]


def test_suggestion_carries_urgency_planned_minutes_and_reason():
    weekly = task(
        id=5, name="Vacuum", interval_days=7, estimated_minutes=20, done_days_ago=10
    )

    suggestion = plan([weekly], 60, NOW)["suggestions"][0]

    assert suggestion["name"] == "Vacuum"
    assert suggestion["urgency"] == 1.43
    assert suggestion["planned_minutes"] == 20
    assert suggestion["reason"] == "Due every 7 days, last done 10 days ago"


def test_reason_for_recurring_task_that_was_never_done():
    weekly = task(interval_days=7, created_days_ago=2)

    reason = plan([weekly], 60, NOW)["suggestions"][0]["reason"]

    assert reason == "Due every 7 days, never done"


def test_reason_for_one_off_job_counts_days_waiting():
    repair = task(created_days_ago=12)

    reason = plan([repair], 60, NOW)["suggestions"][0]["reason"]

    assert reason == "One-off job, waiting 12 days"


def test_unknown_estimate_counts_as_fifteen_minutes():
    result = plan([task(estimated_minutes=None)], 60, NOW)

    assert result["suggestions"][0]["planned_minutes"] == 15
    assert result["minutes_planned"] == 15


def test_tasks_are_picked_greedily_until_time_runs_out():
    tasks = [
        task(id=1, estimated_minutes=20, created_days_ago=90),
        task(id=2, estimated_minutes=30, created_days_ago=60),
        task(id=3, estimated_minutes=10, created_days_ago=30),
    ]

    result = plan(tasks, 35, NOW)

    assert suggested_ids(result) == [1, 3]
    assert result["minutes_available"] == 35
    assert result["minutes_planned"] == 30


def test_due_task_that_does_not_fit_is_reported_as_too_long():
    tasks = [
        task(id=1, name="Windows", estimated_minutes=60, created_days_ago=90),
        task(id=2, name="Tidy", estimated_minutes=10, created_days_ago=30),
    ]

    result = plan(tasks, 30, NOW)

    assert suggested_ids(result) == [2]
    assert result["due_but_too_long"] == [{"id": 1, "name": "Windows", "minutes": 60}]


def test_at_most_three_are_suggested_and_the_cap_is_not_reported_as_too_long():
    tasks = [task(id=n, created_days_ago=30 + n) for n in range(1, 6)]

    result = plan(tasks, 600, NOW)

    assert len(result["suggestions"]) == 3
    assert result["due_but_too_long"] == []


def test_room_filter_ignores_case_and_surrounding_spaces():
    tasks = [
        task(id=1, room="Kitchen"),
        task(id=2, room="bathroom"),
        task(id=3, room=None),
    ]

    result = plan(tasks, 60, NOW, room="  kitchen ")

    assert suggested_ids(result) == [1]


@pytest.mark.parametrize("minutes", [0, -10])
def test_minutes_must_be_greater_than_zero(minutes):
    with pytest.raises(ValueError):
        plan([], minutes, NOW)
