import json
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from backend.engine.models import GameState, ItemKind, Tile
from backend.engine.world import FORGOTTEN_VAULT_PATH, AreaName, load_world


@pytest.fixture
def world():
    return load_world()


@pytest.fixture
def level_data():
    return json.loads(FORGOTTEN_VAULT_PATH.read_bytes())


def load_edited_level(data):
    # These cases exercise JSON parsing and validation without writing a temp file.
    with patch.object(Path, "read_bytes", return_value=json.dumps(data).encode("utf-8")):
        return load_world("edited_level.json")


def test_forgotten_vault_geometry_and_placement(world):
    assert (world.width, world.height) == (17, 13)
    assert len(world.tiles) == 13
    assert all(len(row) == 17 for row in world.tiles)

    areas = {area.name: set(area.tiles) for area in world.areas}
    assert set(areas) == set(AreaName)
    assert world.start in areas[AreaName.ENTRANCE]
    exit_tile, = areas[AreaName.EXIT]
    x, y = exit_tile
    assert world.tiles[y][x] is Tile.EXIT
    assert world.start != exit_tile

    for item in world.items:
        area = AreaName.VAULT if item.kind == ItemKind.TREASURE else AreaName.STORAGE
        assert item.position in areas[area]
    assert world.doors[0].key_id == "bronze_key"
    assert world.guards[0].decoy_id == "decoy"
    assert world.traps[0].toolkit_id == "toolkit"
    assert world.guards[0].position in areas[AreaName.GUARD_POST]
    assert world.doors[0].position in areas[AreaName.SERVICE_TUNNEL]
    assert world.traps[0].position in areas[AreaName.SERVICE_TUNNEL]
    assert world.interactables[0].id == "entrance_plaque"
    entities = (*world.items, *world.doors, *world.guards, *world.traps, *world.interactables)
    for entity in entities:
        x, y = entity.position
        assert 0 <= x < world.width and 0 <= y < world.height
        assert world.tiles[y][x] is not Tile.WALL


def test_level_can_initialize_independent_sessions(world):
    first = GameState.from_world(world)
    second = GameState.from_world(world)
    first.ground_items.pop("bronze_key")

    assert "bronze_key" in second.ground_items
    assert any(item.id == "bronze_key" for item in world.items)
    with pytest.raises(ValidationError, match="frozen"):
        world.areas[0].tiles = ()


@pytest.fixture
def walk(world):
    def reachable(start, *blocked):
        # Starting at the target on the return trip exercises the same grid in reverse.
        available = {
            (x, y)
            for y, row in enumerate(world.tiles)
            for x, tile in enumerate(row)
            if tile is not Tile.WALL
        } - set(blocked)
        frontier = {start} & available
        visited = set()
        while frontier:
            visited |= frontier
            frontier = {
                (x + dx, y + dy)
                for x, y in frontier
                for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0))
            } & (available - visited)
        return visited

    return reachable


def test_storage_and_gate_approaches_are_accessible_with_empty_inventory(world, walk):
    door, guard, trap = world.doors[0], world.guards[0], world.traps[0]
    safely_reachable = walk(world.start, door.position, guard.position, trap.position)
    for item in world.items:
        if item.kind != ItemKind.TREASURE:
            assert item.position in safely_reachable
    for gate in (door, guard):
        x, y = gate.position
        assert any(abs(x - sx) + abs(y - sy) == 1 for sx, sy in safely_reachable)

    # The unopened routes stay blocked even if the player is willing to take trap damage.
    treasure = next(item.position for item in world.items if item.kind == ItemKind.TREASURE)
    assert treasure not in walk(world.start, door.position, guard.position)


@pytest.mark.parametrize("route", [AreaName.GUARD_POST, AreaName.SERVICE_TUNNEL])
def test_each_route_reaches_treasure_and_returns_to_exit(world, walk, route):
    door, guard, trap = world.doors[0], world.guards[0], world.traps[0]
    treasure = next(item.position for item in world.items if item.kind == ItemKind.TREASURE)
    exit_tile, = next(area.tiles for area in world.areas if area.name == AreaName.EXIT)

    if route == AreaName.GUARD_POST:
        blocked = (door.position, trap.position)
    else:
        # The door is open, but the armed trap still blocks a damage-free traversal.
        before_disarm = walk(world.start, guard.position, trap.position)
        assert treasure not in before_disarm
        x, y = trap.position
        assert any(abs(x - sx) + abs(y - sy) == 1 for sx, sy in before_disarm)
        blocked = (guard.position,)

    assert treasure in walk(world.start, *blocked)
    assert exit_tile in walk(treasure, *blocked)


@pytest.mark.parametrize(
    ("area_name", "y", "columns", "error"),
    [
        ("Guard Post", 2, (9, 10, 11), "treasure must be behind"),
        ("Service Tunnel", 10, (8, 9, 10), "treasure must be behind"),
        ("Service Tunnel", 10, (10, 11, 12), "must pass through the armed trap"),
    ],
)
def test_loader_rejects_bypasses(level_data, area_name, y, columns, error):
    area = next(area for area in level_data["areas"] if area["name"] == area_name)
    for x in columns:
        level_data["tiles"][y][x] = "."
        area["tiles"].append([x, y])
    with pytest.raises(ValidationError, match=error):
        load_edited_level(level_data)


@pytest.mark.parametrize(
    ("change", "error"),
    [
        (lambda data: data["tiles"][0].pop(), "tile grid must match"),
        (lambda data: data["areas"].pop(), "seven areas"),
        (lambda data: data["items"][0].update(position=[17, 8]), "in-bounds"),
        (lambda data: data["interactables"][0].update(position=[0, 0]), "non-wall"),
        (lambda data: data.update(start=[1, 6]), "start and exit"),
        (
            lambda data: data["items"][0].update(position=[7, 9]),
            "bronze_key must be in Storage",
        ),
    ],
)
def test_loader_rejects_invalid_geometry_and_placement(level_data, change, error):
    change(level_data)

    with pytest.raises(ValidationError, match=error):
        load_edited_level(level_data)


def test_loader_rejects_a_disconnected_route(level_data):
    tunnel = next(area for area in level_data["areas"] if area["name"] == "Service Tunnel")
    tunnel["tiles"].remove([13, 8])
    level_data["tiles"][8][13] = "#"
    with pytest.raises(ValidationError, match="two intended Vault routes"):
        load_edited_level(level_data)
