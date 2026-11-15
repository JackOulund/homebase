from datetime import datetime
from typing import Any

Task = dict[str, Any]

DUE_URGENCY = 0.9
ONE_OFF_WAITING_DAYS = 30
UNKNOWN_ESTIMATE_MINUTES = 15
MAX_SUGGESTIONS = 3


def days_between(earlier_iso: str, later: datetime) -> float:
    return (later - datetime.fromisoformat(earlier_iso)).total_seconds() / 86400


def urgency(task: Task, now: datetime) -> float:
    interval_days = task["interval_days"]
    if interval_days is None:
        return 1.0 + days_between(task["created_at"], now) / ONE_OFF_WAITING_DAYS
    if task["last_done_at"] is None:
        return 1.0 + days_between(task["created_at"], now) / interval_days
    return days_between(task["last_done_at"], now) / interval_days


def minutes_needed(task: Task) -> int:
    return task["estimated_minutes"] or UNKNOWN_ESTIMATE_MINUTES


def reason_for(task: Task, now: datetime) -> str:
    if task["interval_days"] is None:
        waiting = int(days_between(task["created_at"], now))
        return f"One-off job, waiting {waiting} days"
    prefix = f"Due every {task['interval_days']} days"
    if task["last_done_at"] is None:
        return f"{prefix}, never done"
    return (
        f"{prefix}, last done {int(days_between(task['last_done_at'], now))} days ago"
    )


def in_room(task: Task, room: str) -> bool:
    return (task["room"] or "").strip().lower() == room.strip().lower()


def plan(
    tasks: list[Task], minutes: int, now: datetime, room: str | None = None
) -> dict[str, Any]:
    if minutes <= 0:
        raise ValueError("minutes must be greater than zero")
    candidates = [task for task in tasks if room is None or in_room(task, room)]
    due = sorted(
        ((urgency(task, now), task) for task in candidates),
        key=lambda scored: (-scored[0], scored[1]["id"]),
    )
    due = [(score, task) for score, task in due if score >= DUE_URGENCY]

    suggestions: list[Task] = []
    too_long: list[dict[str, Any]] = []
    minutes_left = minutes
    for score, task in due:
        needed = minutes_needed(task)
        if needed > minutes_left:
            too_long.append({"id": task["id"], "name": task["name"], "minutes": needed})
        elif len(suggestions) < MAX_SUGGESTIONS:
            minutes_left -= needed
            suggestions.append(
                {
                    **task,
                    "urgency": round(score, 2),
                    "planned_minutes": needed,
                    "reason": reason_for(task, now),
                }
            )
    return {
        "minutes_available": minutes,
        "minutes_planned": minutes - minutes_left,
        "suggestions": suggestions,
        "due_but_too_long": too_long,
    }
