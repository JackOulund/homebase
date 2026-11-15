import sqlalchemy as sa
from alembic import context

from homebase.db import metadata


def run_migrations() -> None:
    engine = sa.create_engine(context.config.get_main_option("sqlalchemy.url"))
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()
