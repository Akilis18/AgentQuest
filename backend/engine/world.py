"""Load and validate the Forgotten Vault reference level."""

from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator

from .models import (
    Coordinate,
    Definition,
    EntityDefinition,
    ItemKind,
    Tile,
    WorldDefinition,
)


FORGOTTEN_VAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "forgotten_vault.json"


class AreaName(StrEnum):
    ENTRANCE = "Entrance"
    JUNCTION = "Junction"
    STORAGE = "Storage"
    GUARD_POST = "Guard Post"
    SERVICE_TUNNEL = "Service Tunnel"
    VAULT = "Vault"
    EXIT = "Exit"


AREA_CONNECTIONS = {
    frozenset(pair)
    for pair in (
        (AreaName.ENTRANCE, AreaName.EXIT),
        (AreaName.ENTRANCE, AreaName.JUNCTION),
        (AreaName.JUNCTION, AreaName.STORAGE),
        (AreaName.JUNCTION, AreaName.GUARD_POST),
        (AreaName.JUNCTION, AreaName.SERVICE_TUNNEL),
        (AreaName.GUARD_POST, AreaName.VAULT),
        (AreaName.SERVICE_TUNNEL, AreaName.VAULT),
    )
}


class AreaDefinition(Definition):
    name: AreaName
    tiles: tuple[Coordinate, ...] = Field(min_length=1)


class InteractableDefinition(EntityDefinition):
    description: str = Field(min_length=1)


def _neighbors(position: Coordinate) -> Iterator[Coordinate]:
    x, y = position
    yield x + 1, y
    yield x - 1, y
    yield x, y + 1
    yield x, y - 1


def _reachable(start: Coordinate, walkable: set[Coordinate]) -> set[Coordinate]:
    reached = set()
    pending = [start] if start in walkable else []
    while pending:
        position = pending.pop()
        if position in reached:
            continue
        reached.add(position)
        pending.extend(tile for tile in _neighbors(position) if tile in walkable)
    return reached


def _resolve_route(
    start: Coordinate,
    walkable: set[Coordinate],
    blocked: set[Coordinate],
    tools: dict[Coordinate, Coordinate],
) -> set[Coordinate]:
    """Return safe walkable tiles after acquiring and applying available tools.

    Reaching an item tile permits pickup. Reaching a cardinal neighbor of an
    obstacle permits use. Resolving an obstacle only adds movement options.
    Each route starts fresh and enables at most one use of the Decoy.
    """
    while True:
        reached = _reachable(start, walkable - blocked)
        opened = {
            obstacle
            for obstacle in blocked & tools.keys()
            if tools[obstacle] in reached and reached.intersection(_neighbors(obstacle))
        }
        if not opened:
            return walkable - blocked
        blocked = blocked - opened


class ForgottenVaultDefinition(WorldDefinition):
    areas: tuple[AreaDefinition, ...]
    interactables: tuple[InteractableDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_forgotten_vault(self) -> Self:
        if self.id != "forgotten_vault" or (self.width, self.height) != (17, 13):
            raise ValueError("Forgotten Vault must have ID forgotten_vault and a 17×13 grid")

        walkable = {
            (x, y)
            for y, row in enumerate(self.tiles)
            for x, tile in enumerate(row)
            if tile != Tile.WALL
        }
        exit_tile = next(
            (x, y)
            for x, y in walkable
            if self.tiles[y][x] == Tile.EXIT
        )
        area_at = self._validate_areas(walkable)
        if area_at[self.start] != AreaName.ENTRANCE or area_at[exit_tile] != AreaName.EXIT:
            raise ValueError("start and exit must be in the Entrance and Exit areas")

        self._validate_entities(area_at)
        self._validate_routes(walkable, exit_tile)
        return self

    def _validate_areas(self, walkable: set[Coordinate]) -> dict[Coordinate, AreaName]:
        names = {area.name for area in self.areas}
        if names != set(AreaName) or len(self.areas) != len(names):
            raise ValueError("each of the seven areas must be defined exactly once")

        area_at: dict[Coordinate, AreaName] = {}
        for area in self.areas:
            tiles = set(area.tiles)
            if not tiles <= walkable or len(tiles) != len(area.tiles) or tiles & area_at.keys():
                raise ValueError(f"{area.name} must contain unique walkable tiles")
            if _reachable(area.tiles[0], tiles) != tiles:
                raise ValueError(f"{area.name} must be connected by cardinal movement")
            area_at.update(dict.fromkeys(tiles, area.name))
        if area_at.keys() != walkable:
            raise ValueError("every walkable tile must belong to an area")

        connections = {
            frozenset((area, area_at[neighbor]))
            for tile, area in area_at.items()
            for neighbor in _neighbors(tile)
            if neighbor in area_at and area_at[neighbor] != area
        }
        if connections != AREA_CONNECTIONS:
            raise ValueError("area connections must form the two intended Vault routes")
        return area_at

    def _validate_entities(self, area_at: dict[Coordinate, AreaName]) -> None:
        kinds = {item.kind for item in self.items}
        if kinds != set(ItemKind) or len(self.items) != len(kinds):
            raise ValueError("Forgotten Vault requires one item of each kind")
        if len(self.doors) != 1 or len(self.guards) != 1 or len(self.traps) != 1:
            raise ValueError("Forgotten Vault requires one door, one guard, and one trap")

        item_placements = tuple(
            (item, AreaName.VAULT if item.kind == ItemKind.TREASURE else AreaName.STORAGE)
            for item in self.items
        )
        placements = (
            *item_placements,
            (self.doors[0], AreaName.SERVICE_TUNNEL),
            (self.guards[0], AreaName.GUARD_POST),
            (self.traps[0], AreaName.SERVICE_TUNNEL),
        )
        for entity, area in placements:
            if area_at[entity.position] != area:
                raise ValueError(f"{entity.id} must be in {area}")

        entities = (*self.items, *self.doors, *self.guards, *self.traps, *self.interactables)
        if len({entity.id for entity in entities}) != len(entities):
            raise ValueError("entity IDs must be unique, including interactables")
        if self.doors[0].position == self.traps[0].position:
            raise ValueError("the locked door and trap must occupy distinct tiles")
        for entity in self.interactables:
            self._validate_position(entity.position, entity.id)

    def _validate_routes(self, walkable: set[Coordinate], exit_tile: Coordinate) -> None:
        door, guard, trap = self.doors[0], self.guards[0], self.traps[0]
        item_positions = {item.id: item.position for item in self.items}
        treasure = next(item.position for item in self.items if item.kind == ItemKind.TREASURE)
        gates = {door.position, guard.position}
        initial = _reachable(self.start, walkable - gates)
        if exit_tile not in initial:
            raise ValueError("Exit must be reachable directly from Entrance")
        if treasure in initial:
            raise ValueError("treasure must be behind the guard or the locked door")

        blocked = gates | {trap.position}
        safe_start = _reachable(self.start, walkable - blocked)
        storage_items = {item.position for item in self.items if item.kind != ItemKind.TREASURE}
        if not storage_items <= safe_start:
            raise ValueError("Storage items must be safely reachable before using any item")

        guard_tools = {guard.position: item_positions[guard.decoy_id]}
        service_tools = {door.position: item_positions[door.key_id]}
        service_without_toolkit = _resolve_route(self.start, walkable, blocked, service_tools)
        if treasure in _reachable(self.start, service_without_toolkit):
            raise ValueError("Service Tunnel must pass through the armed trap")
        service_tools[trap.position] = item_positions[trap.toolkit_id]

        for area, tools in (
            (AreaName.GUARD_POST, guard_tools),
            (AreaName.SERVICE_TUNNEL, service_tools),
        ):
            safe_tiles = _resolve_route(self.start, walkable, blocked, tools)
            if treasure not in _reachable(self.start, safe_tiles):
                raise ValueError(f"{area} must independently reach treasure safely")
            if exit_tile not in _reachable(treasure, safe_tiles):
                raise ValueError(f"{area} must allow returning to Exit with the treasure")


def load_world(path: str | Path = FORGOTTEN_VAULT_PATH) -> ForgottenVaultDefinition:
    """Load the reference level or validate an edited copy of its JSON."""
    return ForgottenVaultDefinition.model_validate_json(Path(path).read_bytes())
