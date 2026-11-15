from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from homebase.db import task_completions, tasks

Task = dict[str, Any]

still_open = sa.and_(
    tasks.c.archived_at.is_(None),
    sa.or_(tasks.c.interval_days.is_not(None), tasks.c.last_done_at.is_(None)),
)


class TaskStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def add(
        self,
        name: str,
        estimated_minutes: int | None = None,
        interval_days: int | None = None,
        room: str | None = None,
        notes: str | None = None,
    ) -> Task:
        values = {
            "name": required_text("name", name),
            "estimated_minutes": positive_or_none(
                "estimated_minutes", estimated_minutes
            ),
            "interval_days": positive_or_none("interval_days", interval_days),
            "room": text_or_none(room),
            "notes": text_or_none(notes),
        }
        async with self._engine.begin() as connection:
            result = await connection.execute(
                sa.insert(tasks).values(**values).returning(tasks)
            )
            return as_task(result.one())

    async def list_open(self) -> list[Task]:
        async with self._engine.connect() as connection:
            result = await connection.execute(
                sa.select(tasks).where(still_open).order_by(tasks.c.id)
            )
            return [as_task(row) for row in result]

    async def complete(self, task_id: int, actual_minutes: int | None = None) -> dict:
        positive_or_none("actual_minutes", actual_minutes)
        async with self._engine.begin() as connection:
            updated = await connection.execute(
                sa.update(tasks)
                .where(tasks.c.id == task_id, still_open)
                .values(last_done_at=sa.func.now())
                .returning(tasks)
            )
            row = updated.one_or_none()
            if row is None:
                raise ValueError(f"There is no open task with id {task_id}")
            await connection.execute(
                sa.insert(task_completions).values(
                    task_id=task_id, actual_minutes=actual_minutes
                )
            )
            statistics = await connection.execute(
                sa.select(
                    sa.func.count().label("times_done"),
                    sa.func.avg(task_completions.c.actual_minutes).label("average"),
                ).where(task_completions.c.task_id == task_id)
            )
            times_done, average = statistics.one()
            return {
                "task": as_task(row),
                "actual_minutes": actual_minutes,
                "times_done": times_done,
                "average_actual_minutes": rounded_or_none(average),
            }

    async def time_history(self) -> list[dict]:
        timed = task_completions.c.actual_minutes.is_not(None)
        async with self._engine.connect() as connection:
            result = await connection.execute(
                sa.select(
                    tasks.c.id,
                    tasks.c.name,
                    tasks.c.room,
                    tasks.c.estimated_minutes,
                    sa.func.count().label("times_done"),
                    sa.func.avg(task_completions.c.actual_minutes).label("average"),
                )
                .select_from(tasks.join(task_completions))
                .where(tasks.c.archived_at.is_(None), timed)
                .group_by(tasks.c.id)
                .order_by(tasks.c.id)
            )
            return [
                {
                    "id": row.id,
                    "name": row.name,
                    "room": row.room,
                    "estimated_minutes": row.estimated_minutes,
                    "times_done": row.times_done,
                    "average_actual_minutes": rounded_or_none(row.average),
                }
                for row in result
            ]

    async def update(
        self,
        task_id: int,
        name: str | None = None,
        estimated_minutes: int | None = None,
        interval_days: int | None = None,
        room: str | None = None,
        notes: str | None = None,
    ) -> Task:
        changes = {
            "name": None if name is None else required_text("name", name),
            "estimated_minutes": positive_or_none(
                "estimated_minutes", estimated_minutes
            ),
            "interval_days": positive_or_none("interval_days", interval_days),
            "room": text_or_none(room),
            "notes": text_or_none(notes),
        }
        given = {field: value for field, value in changes.items() if value is not None}
        if not given:
            raise ValueError("Give at least one field to change")
        async with self._engine.begin() as connection:
            result = await connection.execute(
                sa.update(tasks)
                .where(tasks.c.id == task_id, tasks.c.archived_at.is_(None))
                .values(**given)
                .returning(tasks)
            )
            return as_task(one_or_missing(result, task_id))

    async def remove(self, task_id: int) -> Task:
        async with self._engine.begin() as connection:
            result = await connection.execute(
                sa.update(tasks)
                .where(tasks.c.id == task_id, tasks.c.archived_at.is_(None))
                .values(archived_at=sa.func.now())
                .returning(tasks)
            )
            return as_task(one_or_missing(result, task_id))


def one_or_missing(result: sa.Result, task_id: int) -> sa.Row:
    row = result.one_or_none()
    if row is None:
        raise ValueError(f"There is no task with id {task_id}")
    return row


def rounded_or_none(value: Any) -> int | None:
    return None if value is None else round(value)


def required_text(field: str, value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} must not be empty")
    return cleaned


def text_or_none(value: str | None) -> str | None:
    return (value or "").strip() or None


def positive_or_none(field: str, value: int | None) -> int | None:
    if value is not None and value <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return value


def as_task(row: sa.Row) -> Task:
    return {
        "id": row.id,
        "name": row.name,
        "notes": row.notes,
        "room": row.room,
        "estimated_minutes": row.estimated_minutes,
        "interval_days": row.interval_days,
        "created_at": row.created_at.isoformat(),
        "last_done_at": row.last_done_at.isoformat() if row.last_done_at else None,
    }
