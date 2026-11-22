"""FastAPI entry point for the AgentQuest backend."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .engine.session import GameSessions
from .engine.world import load_world


def create_app() -> FastAPI:
    app = FastAPI(title="AgentQuest")
    app.state.games = GameSessions(load_world())
    app.include_router(router)
    frontend = Path(__file__).resolve().parents[1] / "frontend"
    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = create_app()
