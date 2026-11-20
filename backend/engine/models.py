"""Validated world data, private session state, and the shared action contract."""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
Identifier = Annotated[str, Field(strict=True, min_length=1, pattern=r"^\S+$")]
# JSON uses [x, y], with (0, 0) at the top left and grid access as tiles[y][x].
Coordinate = tuple[NonNegativeInt, NonNegativeInt]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Definition(Model):
    model_config = ConfigDict(frozen=True)


class Tile(StrEnum):
    FLOOR = "."
    WALL = "#"
    EXIT = "E"


class ItemKind(StrEnum):
    KEY = "key"
    TOOLKIT = "toolkit"
    DECOY = "decoy"
    TREASURE = "treasure"


class EntityDefinition(Definition):
    id: Identifier
    position: Coordinate


class ItemDefinition(EntityDefinition):
    kind: ItemKind


class DoorDefinition(EntityDefinition):
    key_id: Identifier


class GuardDefinition(EntityDefinition):
    decoy_id: Identifier


class TrapDefinition(EntityDefinition):
    toolkit_id: Identifier


class WorldDefinition(Definition):
    id: Identifier
    width: PositiveInt
    height: PositiveInt
    tiles: tuple[tuple[Tile, ...], ...]
    start: Coordinate
    items: tuple[ItemDefinition, ...] = ()
    doors: tuple[DoorDefinition, ...] = ()
    guards: tuple[GuardDefinition, ...] = ()
    traps: tuple[TrapDefinition, ...] = ()

    @model_validator(mode="after")
    def validate_layout(self) -> Self:
        if len(self.tiles) != self.height or any(
            len(row) != self.width for row in self.tiles
        ):
            raise ValueError("tile grid must match width and height")
        if sum(row.count(Tile.EXIT) for row in self.tiles) != 1:
            raise ValueError("tile grid must contain exactly one exit")

        self._validate_position(self.start, "start")
        entities = (*self.items, *self.doors, *self.guards, *self.traps)
        ids = set()
        for entity in entities:
            if entity.id in ids:
                raise ValueError(f"duplicate entity ID: {entity.id}")
            ids.add(entity.id)
            self._validate_position(entity.position, entity.id)

        item_kinds = {item.id: item.kind for item in self.items}
        requirements = (
            *((door.id, door.key_id, ItemKind.KEY) for door in self.doors),
            *((guard.id, guard.decoy_id, ItemKind.DECOY) for guard in self.guards),
            *((trap.id, trap.toolkit_id, ItemKind.TOOLKIT) for trap in self.traps),
        )
        for entity_id, item_id, kind in requirements:
            if item_kinds.get(item_id) != kind:
                raise ValueError(f"{entity_id} must reference a {kind} item")
        return self

    def _validate_position(self, position: Coordinate, label: str) -> None:
        x, y = position
        if x >= self.width or y >= self.height or self.tiles[y][x] == Tile.WALL:
            raise ValueError(f"{label} must be on an in-bounds non-wall tile")


class GameStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    VICTORY = "victory"
    DEFEAT = "defeat"


class GameState(Model):
    """Authoritative session data. Public observations will be projected separately."""

    world_id: Identifier
    position: Coordinate
    health: Annotated[int, Field(strict=True, ge=0, le=3)] = 3
    turn: NonNegativeInt = 0
    status: GameStatus = GameStatus.IN_PROGRESS
    inventory: set[Identifier] = Field(default_factory=set)
    ground_items: dict[Identifier, Coordinate] = Field(default_factory=dict)
    unlocked_doors: set[Identifier] = Field(default_factory=set)
    distracted_guards: set[Identifier] = Field(default_factory=set)
    disarmed_traps: set[Identifier] = Field(default_factory=set)
    discovered_tiles: set[Coordinate] = Field(default_factory=set)

    @classmethod
    def from_world(cls, world: WorldDefinition) -> Self:
        return cls(
            world_id=world.id,
            position=world.start,
            ground_items={item.id: item.position for item in world.items},
        )


class Direction(StrEnum):
    NORTH = "north"
    EAST = "east"
    SOUTH = "south"
    WEST = "west"


class MoveAction(Model):
    type: Literal["move"]
    direction: Direction


class InspectAction(Model):
    type: Literal["inspect"]
    target: Identifier | Coordinate


class PickupAction(Model):
    type: Literal["pickup"]
    item_id: Identifier


class UseItemAction(Model):
    type: Literal["use_item"]
    item_id: Identifier
    target: Identifier | Coordinate


class InteractAction(Model):
    type: Literal["interact"]
    target: Identifier | Coordinate


Action = Annotated[
    MoveAction | InspectAction | PickupAction | UseItemAction | InteractAction,
    Field(discriminator="type"),
]


class ActionRequest(Model):
    request_id: Identifier
    expected_turn: NonNegativeInt
    action: Action


class ActionStatus(StrEnum):
    APPLIED = "applied"
    BLOCKED = "blocked"
    REJECTED = "rejected"


class ActionResult(Definition):
    request_id: Identifier
    status: ActionStatus
    turn: NonNegativeInt

    @property
    def turn_consumed(self) -> bool:
        """Accepted attempts consume a turn, including rule-blocked attempts."""
        return self.status in (ActionStatus.APPLIED, ActionStatus.BLOCKED)
