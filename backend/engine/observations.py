"""Project authoritative state into current sight and last-seen memory."""

from .models import (
    ActionStatus,
    Coordinate,
    Definition,
    GameState,
    GameStatus,
    InspectAction,
    KnownObject,
    Tile,
    WorldDefinition,
)
from .rules import Outcome, neighbors, tile_at


class ObservedTile(Definition):
    position: Coordinate
    tile: Tile
    visible: bool


class Observation(Definition):
    position: Coordinate
    health: int
    turn: int
    status: GameStatus
    inventory: tuple[str, ...]
    tiles: tuple[ObservedTile, ...]
    objects: tuple[KnownObject, ...]


def visible_tiles(world: WorldDefinition, position: Coordinate) -> set[Coordinate]:
    # A cardinal step has no intervening tile. Adjacent walls are visible,
    # and sight never continues through them or around corners.
    return {
        tile for tile in (position, *neighbors(position)) if tile_at(world, tile) is not None
    }


def _visible_objects(
    world: WorldDefinition, state: GameState, visible: set[Coordinate]
) -> tuple[KnownObject, ...]:
    objects = [
        KnownObject(id=item.id, position=position, kind="item", item_kind=item.kind)
        for item in world.items
        if (position := state.ground_items.get(item.id)) is not None and position in visible
    ]
    objects.extend(
        KnownObject(id=door.id, position=door.position, kind="door",
                    status="unlocked" if door.id in state.unlocked_doors else "locked")
        for door in world.doors if door.position in visible
    )
    objects.extend(
        KnownObject(id=guard.id, position=guard.position, kind="guard",
                    status="distracted" if guard.id in state.distracted_guards else "alert")
        for guard in world.guards if guard.position in visible
    )
    objects.extend(
        KnownObject(id=trap.id, position=trap.position, kind="trap",
                    status="disarmed" if trap.id in state.disarmed_traps else "armed")
        for trap in world.traps if trap.position in visible
    )
    objects.extend(
        KnownObject(id=entity.id, position=entity.position, kind="interactable")
        for entity in world.interactables if entity.position in visible
    )
    return tuple(objects)


def remember_visible(world: WorldDefinition, state: GameState) -> None:
    visible = visible_tiles(world, state.position)
    state.discovered_tiles.update(visible)
    state.known_objects = {
        object_id: obj for object_id, obj in state.known_objects.items()
        if obj.position not in visible
    }
    state.known_objects.update({obj.id: obj for obj in _visible_objects(world, state, visible)})


def observe(world: WorldDefinition, state: GameState) -> Observation:
    visible = visible_tiles(world, state.position)
    return Observation(
        position=state.position,
        health=state.health,
        turn=state.turn,
        status=state.status,
        inventory=tuple(sorted(state.inventory)),
        tiles=tuple(
            ObservedTile(position=(x, y), tile=world.tiles[y][x], visible=(x, y) in visible)
            for x, y in sorted(state.discovered_tiles)
        ),
        objects=tuple(state.known_objects[key] for key in sorted(state.known_objects)),
    )


def _describe(obj: KnownObject) -> str:
    label = obj.id.replace("_", " ").capitalize()
    if obj.kind == "trap":
        return f"{label} is {obj.status}. It deals 1 damage on entry while armed."
    if obj.status is not None:
        return f"{label} is {obj.status}."
    if obj.item_kind is not None:
        return f"{label} ({obj.item_kind}). Pick it up while standing on its tile."
    return f"{label}. You can interact with it."


def inspect(world: WorldDefinition, state: GameState, action: InspectAction) -> Outcome:
    visible = visible_tiles(world, state.position)
    objects = _visible_objects(world, state, visible)
    if isinstance(action.target, str):
        for obj in objects:
            if action.target == obj.id:
                return ActionStatus.APPLIED, _describe(obj)
    elif action.target in visible:
        x, y = action.target
        terrain = {Tile.WALL: "Wall.", Tile.FLOOR: "Floor.", Tile.EXIT: "Exit."}
        descriptions = [terrain[world.tiles[y][x]]]
        descriptions.extend(_describe(obj) for obj in objects if obj.position == action.target)
        return ActionStatus.APPLIED, " ".join(descriptions)
    return ActionStatus.BLOCKED, "That target is outside your current view."
