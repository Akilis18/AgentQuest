"""Serialize requests and own all mutable state for one game session."""

from collections.abc import Mapping
from threading import Lock
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError

from .actions import execute_action
from .models import (
    ActionRecord,
    ActionRequest,
    ActionResult,
    ActionStatus,
    GameState,
    GameStatus,
    Identifier,
    WorldDefinition,
)
from .observations import Observation, observe, remember_visible


_REQUEST_ID = TypeAdapter(Identifier)


class GameSession:
    def __init__(self, world: WorldDefinition, *, replay_requests: bool = False):
        self._world = world
        self._lock = Lock()
        self._history: dict[str, ActionRecord] = {}
        # API receipts survive restart so a delayed retry cannot act in a new game.
        self._receipts: dict[str, ActionRecord] | None = {} if replay_requests else None
        self._state = GameState.from_world(world)
        remember_visible(self._world, self._state)

    def observation(self) -> Observation:
        with self._lock:
            return observe(self._world, self._state)

    def history(self) -> tuple[ActionRecord, ...]:
        """Return a detached history of accepted attempts, including blocked actions."""
        with self._lock:
            return tuple(record.model_copy(deep=True) for record in self._history.values())

    def restart(self) -> Observation:
        with self._lock:
            self._state = GameState.from_world(self._world)
            self._history.clear()
            remember_visible(self._world, self._state)
            return observe(self._world, self._state)

    def submit(self, payload: object) -> ActionResult:
        """Validate, serialize, and execute at most one action."""
        with self._lock:
            if isinstance(payload, ActionRequest):
                payload = payload.model_dump(warnings=False)
            try:
                request = ActionRequest.model_validate(payload)
            except ValidationError:
                raw_id = payload.get("request_id") if isinstance(payload, Mapping) else None
                try:
                    request_id = _REQUEST_ID.validate_python(raw_id)
                except ValidationError:
                    request_id = None
                return self._reject(request_id, "Malformed action request.")

            receipts = self._receipts
            previous = (receipts if receipts is not None else self._history).get(request.request_id)
            if previous is not None:
                if receipts is not None and previous.request == request:
                    return previous.result
                return self._reject(request.request_id, "Duplicate request ID.")

            result = self._apply(request)
            record = ActionRecord(request=request, result=result)
            if result.turn_consumed:
                self._history[request.request_id] = record
            if receipts is not None:
                receipts[request.request_id] = record
            return result

    def _apply(self, request: ActionRequest) -> ActionResult:
        if request.expected_turn != self._state.turn:
            return self._reject(request.request_id, "Stale expected turn.")
        if self._state.status != GameStatus.IN_PROGRESS:
            return self._reject(request.request_id, "The game is over. Restart to play again.")

        status, message = execute_action(self._world, self._state, request.action)
        self._state.turn += 1
        remember_visible(self._world, self._state)
        return ActionResult(
            request_id=request.request_id, status=status, turn=self._state.turn, message=message
        )

    def _reject(self, request_id: str | None, message: str) -> ActionResult:
        return ActionResult(
            request_id=request_id, status=ActionStatus.REJECTED, turn=self._state.turn,
            message=message,
        )


class GameSessions:
    """Process-local registry of independent API sessions sharing an immutable world."""

    def __init__(self, world: WorldDefinition):
        self._world = world
        self._lock = Lock()
        self._sessions: dict[str, GameSession] = {}

    def create(self) -> tuple[str, GameSession]:
        session = GameSession(self._world, replay_requests=True)
        with self._lock:
            session_id = str(uuid4())
            while session_id in self._sessions:
                session_id = str(uuid4())
            self._sessions[session_id] = session
        return session_id, session

    def get(self, session_id: str) -> GameSession | None:
        with self._lock:
            return self._sessions.get(session_id)
