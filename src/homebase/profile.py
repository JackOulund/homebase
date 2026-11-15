import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from homebase.db import profile_entries
from homebase.tasks import required_text


class ProfileStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get_all(self) -> dict[str, str]:
        async with self._engine.connect() as connection:
            result = await connection.execute(
                sa.select(profile_entries).order_by(profile_entries.c.key)
            )
            return {row.key: row.value for row in result}

    async def set(self, key: str, value: str) -> None:
        values = {
            "key": normalized_key(key),
            "value": required_text("value", value),
        }
        upsert = insert(profile_entries).values(**values)
        async with self._engine.begin() as connection:
            await connection.execute(
                upsert.on_conflict_do_update(
                    index_elements=[profile_entries.c.key],
                    set_={"value": upsert.excluded.value, "updated_at": sa.func.now()},
                )
            )

    async def remove(self, key: str) -> None:
        cleaned_key = normalized_key(key)
        async with self._engine.begin() as connection:
            result = await connection.execute(
                sa.delete(profile_entries).where(profile_entries.c.key == cleaned_key)
            )
            if result.rowcount == 0:
                raise ValueError(f"There is no profile entry named {cleaned_key}")


def normalized_key(key: str) -> str:
    return required_text("key", key).lower()
