from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine

from homebase.mcp_server import build_mcp_app
from homebase.oauth import HomebaseOAuthProvider
from homebase.profile import ProfileStore
from homebase.settings import Settings
from homebase.tasks import TaskStore


def create_app(settings: Settings) -> FastAPI:
    engine = create_async_engine(settings.database_url)
    mcp_app = build_mcp_app(
        settings,
        HomebaseOAuthProvider(engine, settings),
        TaskStore(engine),
        ProfileStore(engine),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with mcp_app.router.lifespan_context(mcp_app):
            yield
        await engine.dispose()

    api = FastAPI(title="homebase", lifespan=lifespan)

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    api.mount("/", mcp_app)
    return api


app = create_app(Settings.from_environment())
