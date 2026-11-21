"""HTTP envelopes around the shared action and public observation models."""

from typing import Literal

from pydantic import BaseModel

from backend.engine.observations import Observation


class GameResponse(BaseModel):
    session_id: str
    observation: Observation


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ErrorResponse(BaseModel):
    detail: str
