"""Deterministic gameplay rules for an accepted action."""

from collections.abc import Iterator

from .models import (
    ActionStatus,
    Coordinate,
    Direction,
    DoorDefinition,
    GameState,
    GameStatus,
    GuardDefinition,
    InteractAction,
    ItemKind,
    MoveAction,
    PickupAction,
    Tile,
    UseItemAction,
    WorldDefinition,
)


Outcome = tuple[ActionStatus, str]
OFFSETS = {
    Direction.NORTH: (0, -1),
    Direction.EAST: (1, 0),
    Direction.SOUTH: (0, 1),
    Direction.WEST: (-1, 0),
}


def neighbors(position: Coordinate) -> Iterator[Coordinate]:
    x, y = position
    for dx, dy in OFFSETS.values():
        yield x + dx, y + dy


def tile_at(world: WorldDefinition, position: Coordinate) -> Tile | None:
    x, y = position
    if 0 <= x < world.width and 0 <= y < world.height:
        return world.tiles[y][x]
    return None


def in_range(position: Coordinate, target: Coordinate) -> bool:
    return abs(position[0] - target[0]) + abs(position[1] - target[1]) <= 1


def move(world: WorldDefinition, state: GameState, action: MoveAction) -> Outcome:
    x, y = state.position
    dx, dy = OFFSETS[action.direction]
    destination = (x + dx, y + dy)
    tile = tile_at(world, destination)
    if tile is None or tile == Tile.WALL:
        return ActionStatus.BLOCKED, "Terrain blocks the way."
    if any(
        door.position == destination and door.id not in state.unlocked_doors
        for door in world.doors
    ):
        return ActionStatus.BLOCKED, "A locked door blocks the way."
    if any(
        guard.position == destination and guard.id not in state.distracted_guards
        for guard in world.guards
    ):
        return ActionStatus.BLOCKED, "An alert guard blocks the way."

    state.position = destination
    if any(
        trap.position == destination and trap.id not in state.disarmed_traps
        for trap in world.traps
    ):
        state.health -= 1
        if state.health == 0:
            state.status = GameStatus.DEFEAT
            return ActionStatus.APPLIED, "The trap dealt 1 damage. You were defeated."
        message = "Moved onto an armed trap and took 1 damage."
    else:
        message = "Moved one tile."

    if tile == Tile.EXIT and any(
        item.kind == ItemKind.TREASURE and item.id in state.inventory for item in world.items
    ):
        state.status = GameStatus.VICTORY
        return ActionStatus.APPLIED, f"{message} You escaped with the treasure."
    return ActionStatus.APPLIED, message


def pickup(state: GameState, action: PickupAction) -> Outcome:
    if state.ground_items.get(action.item_id) != state.position:
        return ActionStatus.BLOCKED, "That item is not on your tile."
    del state.ground_items[action.item_id]
    state.inventory.add(action.item_id)
    return ActionStatus.APPLIED, f"Picked up {action.item_id}."


def use_item(world: WorldDefinition, state: GameState, action: UseItemAction) -> Outcome:
    if action.item_id not in state.inventory:
        return ActionStatus.BLOCKED, "You do not own that item."

    candidates = (
        *((door, door.key_id) for door in world.doors),
        *((guard, guard.decoy_id) for guard in world.guards),
        *((trap, trap.toolkit_id) for trap in world.traps),
    )
    matches = [
        entity for entity, item_id in candidates
        if item_id == action.item_id
        and action.target in (entity.id, entity.position)
        and in_range(state.position, entity.position)
    ]
    if len(matches) != 1:
        return ActionStatus.BLOCKED, "No unique compatible target is in reach."

    target = matches[0]
    if isinstance(target, DoorDefinition):
        if target.id in state.unlocked_doors:
            return ActionStatus.BLOCKED, "The door is already unlocked."
        state.unlocked_doors.add(target.id)
        return ActionStatus.APPLIED, "Unlocked the door."
    if isinstance(target, GuardDefinition):
        if target.id in state.distracted_guards:
            return ActionStatus.BLOCKED, "The guard is already distracted."
        state.distracted_guards.add(target.id)
        state.inventory.remove(action.item_id)
        return ActionStatus.APPLIED, "Distracted the guard and consumed the Decoy."
    if target.id in state.disarmed_traps:
        return ActionStatus.BLOCKED, "The trap is already disarmed."
    state.disarmed_traps.add(target.id)
    return ActionStatus.APPLIED, "Disarmed the trap."


def interact(world: WorldDefinition, state: GameState, action: InteractAction) -> Outcome:
    matches = [
        entity for entity in world.interactables
        if action.target in (entity.id, entity.position) and in_range(state.position, entity.position)
    ]
    if len(matches) != 1:
        return ActionStatus.BLOCKED, "No unique environmental interaction is in reach."
    return ActionStatus.APPLIED, matches[0].description
