import pytest
from pydantic import ValidationError

from backend.engine.models import (
    ActionRequest,
    ActionResult,
    GameState,
    GameStatus,
    Tile,
    WorldDefinition,
)


@pytest.fixture
def world_data():
    return {
        "id": "test",
        "width": 3,
        "height": 2,
        "tiles": [[".", "#", "E"], [".", ".", "."]],
        "start": [0, 1],
        "items": [
            {"id": "key", "kind": "key", "position": [0, 1]},
            {"id": "decoy", "kind": "decoy", "position": [0, 1]},
            {"id": "toolkit", "kind": "toolkit", "position": [0, 1]},
            {"id": "treasure", "kind": "treasure", "position": [2, 1]},
        ],
        "doors": [{"id": "door", "key_id": "key", "position": [2, 1]}],
        "guards": [{"id": "guard", "decoy_id": "decoy", "position": [1, 1]}],
        "traps": [{"id": "trap", "toolkit_id": "toolkit", "position": [1, 1]}],
    }


def test_world_and_session_initialization(world_data):
    world = WorldDefinition.model_validate(world_data)
    state = GameState.from_world(world)

    assert world.tiles[0][2] is Tile.EXIT
    assert WorldDefinition.model_validate_json(world.model_dump_json()) == world
    assert state.world_id == world.id
    assert state.position == (0, 1)
    assert (state.health, state.turn, state.status) == (3, 0, GameStatus.IN_PROGRESS)
    assert state.ground_items == {item.id: item.position for item in world.items}
    assert not state.inventory


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"height": 3}, "tile grid must match"),
        ({"tiles": [[".", "?", "E"], [".", ".", "."]]}, "Input should be"),
        ({"tiles": [[".", "#", "."], [".", ".", "."]]}, "exactly one exit"),
        ({"start": [1, 0]}, "non-wall"),
        ({"start": [0, 2]}, "in-bounds"),
        ({"start": [-1, 0]}, "greater than or equal"),
        ({"start": [True, 0]}, "valid integer"),
        (
            {"doors": [{"id": "key", "key_id": "key", "position": [2, 1]}]},
            "duplicate entity ID",
        ),
        (
            {"doors": [{"id": "door", "key_id": "decoy", "position": [2, 1]}]},
            "reference a key",
        ),
        (
            {"traps": [{"id": "trap", "toolkit_id": "toolkit", "position": [1, 0]}]},
            "non-wall",
        ),
    ],
)
def test_invalid_world(world_data, changes, error):
    with pytest.raises(ValidationError, match=error):
        WorldDefinition.model_validate(world_data | changes)


def test_session_mutations_leave_other_sessions_and_world_independent(world_data):
    world = WorldDefinition.model_validate(world_data)
    first = GameState.from_world(world)
    second = GameState.from_world(world)

    first.ground_items.pop("key")
    first.inventory.add("key")
    first.unlocked_doors.add("door")
    first.distracted_guards.add("guard")
    first.disarmed_traps.add("trap")
    first.discovered_tiles.add(first.position)
    first.turn += 1

    assert first != second
    assert second == GameState.from_world(world)
    assert second.ground_items["key"] == world.items[0].position
    assert not (
        second.inventory
        or second.unlocked_doors
        or second.distracted_guards
        or second.disarmed_traps
        or second.discovered_tiles
    )
    assert second.turn == 0


@pytest.mark.parametrize(
    "action",
    [
        {"type": "move", "direction": "north"},
        {"type": "inspect", "target": [0, 1]},
        {"type": "pickup", "item_id": "key"},
        {"type": "use_item", "item_id": "key", "target": "door"},
        {"type": "interact", "target": "door"},
    ],
)
def test_action_request_round_trip(action):
    payload = {"request_id": "request-1", "expected_turn": 0, "action": action}
    assert ActionRequest.model_validate(payload).model_dump(mode="json") == payload


@pytest.mark.parametrize(
    "changes",
    [
        {"action": {"type": "move", "direction": "northeast"}},
        {"action": {"type": "move", "direction": "north", "steps": 2}},
        {"action": {"type": "use_item", "item_id": "key"}},
        {"action": {"type": "inspect", "target": [0, 1, 2]}},
        {"action": {"type": "wait"}},
        {"action": [{"type": "move", "direction": "north"}]},
        {"expected_turn": -1},
        {"expected_turn": "0"},
        {"request_id": " "},
    ],
)
def test_invalid_action_request(changes):
    payload = {
        "request_id": "request-1",
        "expected_turn": 0,
        "action": {"type": "move", "direction": "north"},
    }
    with pytest.raises(ValidationError):
        ActionRequest.model_validate(payload | changes)


@pytest.mark.parametrize(
    ("status", "consumed"),
    [("applied", True), ("blocked", True), ("rejected", False)],
)
def test_action_result_turn_consumption(status, consumed):
    result = ActionResult.model_validate(
        {"request_id": "request-1", "status": status, "turn": int(consumed)}
    )
    assert result.turn_consumed is consumed
    assert result.model_dump(mode="json") == {
        "request_id": "request-1",
        "status": status,
        "turn": int(consumed),
        "message": None,
    }
