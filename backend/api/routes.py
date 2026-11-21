"""REST routes for the deterministic game."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from backend.engine.models import ActionRequest, ActionResult, ActionStatus
from backend.engine.session import GameSession, GameSessions

from .schemas import ErrorResponse, GameResponse, HealthResponse


router = APIRouter(prefix="/api")
NOT_FOUND = {404: {"model": ErrorResponse, "description": "Unknown game session"}}


def _sessions(request: Request) -> GameSessions:
    return request.app.state.games


def _session(session_id: str, games: Annotated[GameSessions, Depends(_sessions)]) -> GameSession:
    session = games.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Game session not found.")
    return session


Session = Annotated[GameSession, Depends(_session)]


@router.get("/health")
def health() -> HealthResponse:
    return HealthResponse()


@router.post("/games", status_code=status.HTTP_201_CREATED)
def create_game(games: Annotated[GameSessions, Depends(_sessions)]) -> GameResponse:
    session_id, session = games.create()
    return GameResponse(session_id=session_id, observation=session.observation())


@router.get("/games/{session_id}", responses=NOT_FOUND)
def get_game(session_id: str, session: Session) -> GameResponse:
    return GameResponse(session_id=session_id, observation=session.observation())


@router.post(
    "/games/{session_id}/actions",
    responses={**NOT_FOUND, 409: {"model": ActionResult, "description": "Action rejected"}},
)
def submit_action(action: ActionRequest, session: Session, response: Response) -> ActionResult:
    result = session.submit(action)
    if result.status == ActionStatus.REJECTED:
        response.status_code = status.HTTP_409_CONFLICT
    return result


@router.post("/games/{session_id}/restart", responses=NOT_FOUND)
def restart_game(session_id: str, session: Session) -> GameResponse:
    return GameResponse(session_id=session_id, observation=session.restart())
