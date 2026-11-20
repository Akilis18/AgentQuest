from concurrent.futures import ThreadPoolExecutor
from itertools import count

import pytest

from backend.engine.models import ActionRequest, ActionStatus, GameStatus, Tile
from backend.engine.session import GameSession
from backend.engine.world import load_world


@pytest.fixture
def session():
    return GameSession(load_world())


@pytest.fixture
def act(session):
    ids = count(1)

    def submit(action_type, **arguments):
        return session.submit({
            "request_id": f"request-{next(ids)}",
            "expected_turn": session.observation().turn,
            "action": {"type": action_type, **arguments},
        })

    return submit


def walk(act, directions):
    names = {"n": "north", "e": "east", "s": "south", "w": "west"}
    for direction in directions:
        result = act("move", direction=names[direction])
        assert result.status == ActionStatus.APPLIED, result


def pickup(act, item_id):
    assert act("pickup", item_id=item_id).status == ActionStatus.APPLIED


def test_movement_and_turns(session, act):
    blocked = act("move", direction="north")
    assert (blocked.status, blocked.turn, blocked.turn_consumed) == (ActionStatus.BLOCKED, 1, True)
    assert session.observation().position == (3, 6)

    applied = act("move", direction="west")
    assert (applied.status, applied.turn, applied.turn_consumed) == (ActionStatus.APPLIED, 2, True)
    assert session.observation().position == (2, 6)
    walk(act, "w")
    assert session.observation().position == (1, 6)
    assert session.observation().status == GameStatus.IN_PROGRESS
    assert act("move", direction="west").status == ActionStatus.BLOCKED


def test_pickup_requires_current_tile_and_updates_memory(session, act):
    assert act("pickup", item_id="bronze_key").status == ActionStatus.BLOCKED
    walk(act, "eessw")
    assert any(obj.id == "bronze_key" for obj in session.observation().objects)
    assert act("pickup", item_id="bronze_key").status == ActionStatus.BLOCKED
    walk(act, "w")
    pickup(act, "bronze_key")
    observation = session.observation()
    assert observation.inventory == ("bronze_key",)
    assert all(obj.id != "bronze_key" for obj in observation.objects)
    assert act("pickup", item_id="bronze_key").status == ActionStatus.BLOCKED


def test_service_tunnel_full_playthrough(session, act):
    walk(act, "eessw")
    pickup(act, "toolkit")
    walk(act, "w")
    pickup(act, "bronze_key")
    assert act("use_item", item_id="bronze_key", target="bronze_door").status == ActionStatus.BLOCKED
    walk(act, "eenneessse")
    assert session.observation().position == (8, 9)
    assert "locked door" in act("move", direction="east").message
    assert act("use_item", item_id="toolkit", target="bronze_door").status == ActionStatus.BLOCKED
    assert act("use_item", item_id="bronze_key", target=[9, 9]).status == ActionStatus.APPLIED
    assert next(obj.status for obj in session.observation().objects if obj.id == "bronze_door") == "unlocked"
    assert act("use_item", item_id="bronze_key", target="bronze_door").status == ActionStatus.BLOCKED
    assert session.observation().inventory == ("bronze_key", "toolkit")
    walk(act, "ee")
    assert "1 damage" in act("inspect", target="pressure_plate").message
    assert act("use_item", item_id="toolkit", target="pressure_plate").status == ActionStatus.APPLIED
    assert next(obj.status for obj in session.observation().objects if obj.id == "pressure_plate") == "disarmed"
    assert session.observation().inventory == ("bronze_key", "toolkit")
    walk(act, "eeennnee")
    assert session.observation().position == (15, 6)
    assert "vault_treasure" not in session.observation().inventory
    pickup(act, "vault_treasure")
    walk(act, "wwssswwwwwwnnnwwwwww")
    observation = session.observation()
    assert (observation.position, observation.health, observation.status) == (
        (1, 6), 3, GameStatus.VICTORY,
    )
    assert "escaped" in session.history()[-1].result.message
    assert act("move", direction="east").status == ActionStatus.REJECTED
    assert session.observation() == observation


def test_guard_post_full_playthrough(session, act):
    walk(act, "eesswws")
    pickup(act, "decoy")
    walk(act, "neenneennnee")
    assert session.observation().position == (9, 3)
    assert "alert guard" in act("move", direction="east").message
    assert act("use_item", item_id="decoy", target="pressure_plate").status == ActionStatus.BLOCKED
    assert session.observation().inventory == ("decoy",)
    assert act("use_item", item_id="decoy", target="vault_guard").status == ActionStatus.APPLIED
    assert session.observation().inventory == ()
    assert act("use_item", item_id="decoy", target="vault_guard").status == ActionStatus.BLOCKED
    walk(act, "eeeesssee")
    pickup(act, "vault_treasure")
    walk(act, "wwnnnwwwwwwssswwwwww")
    assert session.observation().status == GameStatus.VICTORY
    assert session.observation().health == 3


def test_unowned_item_armed_trap_damage_and_defeat(session, act):
    walk(act, "eessww")
    pickup(act, "bronze_key")
    walk(act, "eenneessse")
    assert act("use_item", item_id="bronze_key", target="bronze_door").status == ActionStatus.APPLIED
    walk(act, "ee")
    result = act("use_item", item_id="toolkit", target="pressure_plate")
    assert (result.status, result.message) == (ActionStatus.BLOCKED, "You do not own that item.")
    walk(act, "e")
    assert session.observation().health == 2
    assert act("inspect", target=[11, 9]).status == ActionStatus.APPLIED
    assert session.observation().health == 2
    walk(act, "we")
    assert session.observation().health == 1
    walk(act, "we")
    defeated = session.observation()
    assert defeated.health == 0
    assert defeated.status == GameStatus.DEFEAT
    assert act("inspect", target=[11, 9]).status == ActionStatus.REJECTED
    assert session.observation() == defeated


def test_observation_limits_and_interaction(session, act):
    initial = session.observation()
    assert {tile.position for tile in initial.tiles} == {(3, 6), (2, 6), (4, 6), (3, 5), (3, 7)}
    assert {tile.position for tile in initial.tiles if tile.tile == Tile.WALL} == {(3, 5), (3, 7)}
    assert {obj.id for obj in initial.objects} == {"entrance_plaque"}
    assert "ground_items" not in initial.model_dump()
    assert "treasure" in act("interact", target=[4, 6]).message
    assert act("inspect", target=[3, 7]).message == "Wall."
    assert act("inspect", target=[3, 8]).status == ActionStatus.BLOCKED
    hidden = act("inspect", target="vault_treasure")
    unknown = act("inspect", target="missing")
    assert hidden.status == unknown.status == ActionStatus.BLOCKED
    assert hidden.message == unknown.message
    walk(act, "eee")
    observation = session.observation()
    assert any(tile.position == (3, 6) and not tile.visible for tile in observation.tiles)
    assert any(obj.id == "entrance_plaque" for obj in observation.objects)
    assert act("inspect", target="entrance_plaque").status == ActionStatus.BLOCKED
    assert act("interact", target="entrance_plaque").status == ActionStatus.BLOCKED


def test_rejected_requests_preserve_state_and_history(session):
    request = ActionRequest.model_validate({
        "request_id": "first",
        "expected_turn": 0,
        "action": {"type": "move", "direction": "north"},
    })
    assert session.submit(request).status == ActionStatus.BLOCKED
    observation = session.observation()
    history = session.history()
    assert history[0].request.action.model_dump() == {"type": "move", "direction": "north"}
    assert (history[0].result.status, history[0].result.turn) == (ActionStatus.BLOCKED, 1)
    assert session.submit(request.model_dump() | {"expected_turn": 1}).message == "Duplicate request ID."
    stale = request.model_dump() | {"request_id": "second"}
    assert session.submit(stale).message == "Stale expected turn."
    malformed = stale | {
        "expected_turn": 1,
        "action": {"type": "move", "direction": "northeast"},
    }
    result = session.submit(malformed)
    assert (result.status, result.turn, result.turn_consumed) == (ActionStatus.REJECTED, 1, False)
    assert session.submit({}).request_id is None
    assert session.observation() == observation
    assert session.history() == history


def test_retry_cannot_execute_twice_under_concurrent_submission(session):
    request = {
        "request_id": "same-id",
        "expected_turn": 0,
        "action": {"type": "move", "direction": "east"},
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(session.submit, (request, request)))
    assert {result.status for result in results} == {ActionStatus.APPLIED, ActionStatus.REJECTED}
    assert session.observation().position == (4, 6)
    assert session.observation().turn == 1
    assert len(session.history()) == 1


def test_sessions_and_restart_are_independent():
    world = load_world()
    first, second = GameSession(world), GameSession(world)
    initial = second.observation()
    request = {
        "request_id": "first",
        "expected_turn": 0,
        "action": {"type": "move", "direction": "east"},
    }
    assert first.submit(request).status == ActionStatus.APPLIED
    assert second.observation() == initial
    assert second.history() == ()
    assert first.restart() == initial
    assert first.history() == ()
    assert first.submit(request).status == ActionStatus.APPLIED
