import os

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from homebase.app import create_app
from homebase.migrate import upgrade_to_head
from homebase.password import hash_password
from homebase.settings import Settings

ADMIN_DATABASE_URL = os.environ.get(
    "TEST_ADMIN_DATABASE_URL",
    "postgresql+psycopg://homebase:homebase@localhost:54329/homebase",
)
TEST_DATABASE_NAME = "homebase_test"
PUBLIC_URL = "http://localhost:8000"
PASSWORD = "correct horse battery staple"


@pytest.fixture(scope="session")
def database_url() -> str:
    admin_engine = sa.create_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        exists = connection.scalar(
            sa.text("select 1 from pg_database where datname = :name"),
            {"name": TEST_DATABASE_NAME},
        )
        if not exists:
            connection.execute(sa.text(f'create database "{TEST_DATABASE_NAME}"'))
    admin_engine.dispose()

    url = (
        sa.make_url(ADMIN_DATABASE_URL)
        .set(database=TEST_DATABASE_NAME)
        .render_as_string(hide_password=False)
    )
    upgrade_to_head(url)
    return url


@pytest.fixture(scope="session")
def password_hash() -> str:
    return hash_password(PASSWORD)


@pytest.fixture
def settings(database_url: str, password_hash: str) -> Settings:
    return Settings(
        public_url=PUBLIC_URL,
        database_url=database_url,
        login_password_hash=password_hash,
    )


@pytest.fixture
def empty_database(database_url: str) -> None:
    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "truncate tasks, profile_entries, oauth_tokens, oauth_clients "
                "restart identity cascade"
            )
        )
    engine.dispose()


@pytest.fixture
def client(settings: Settings, empty_database: None):
    with TestClient(
        create_app(settings), base_url=PUBLIC_URL, follow_redirects=False
    ) as test_client:
        yield test_client
