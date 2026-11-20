"""Dispatch a single validated action to the engine rules."""

from . import observations, rules
from .models import (
    Action,
    GameState,
    InspectAction,
    InteractAction,
    MoveAction,
    PickupAction,
    WorldDefinition,
)


def execute_action(world: WorldDefinition, state: GameState, action: Action) -> rules.Outcome:
    """Apply one action. GameSession is the request entry point and owns turn checks."""
    if isinstance(action, MoveAction):
        return rules.move(world, state, action)
    if isinstance(action, InspectAction):
        return observations.inspect(world, state, action)
    if isinstance(action, PickupAction):
        return rules.pickup(state, action)
    if isinstance(action, InteractAction):
        return rules.interact(world, state, action)
    return rules.use_item(world, state, action)
