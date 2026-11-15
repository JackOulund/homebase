from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from homebase.db import tasks

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
