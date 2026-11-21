"""FastAPI entry point for the AgentQuest backend."""

from fastapi import FastAPI

from .api.routes import router
from .engine.session import GameSessions
from .engine.world import load_world


def create_app() -> FastAPI:
    app = FastAPI(title="AgentQuest")
    app.state.games = GameSessions(load_world())
    app.include_router(router)
    return app


app = create_app()
