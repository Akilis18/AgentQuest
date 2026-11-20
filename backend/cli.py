"""Temporary terminal runner for the same requests a future API will submit."""

import json
from itertools import count

from .engine.models import Direction
from .engine.session import GameSession
from .engine.world import load_world


DIRECTIONS = {direction.value[0]: direction.value for direction in Direction}


def main() -> None:
    session = GameSession(load_world())
    observation = session.observation()
    print('Enter n/e/s/w, a JSON action object, restart, or quit.')
    print('Example: {"type":"interact","target":"entrance_plaque"}')
    print(observation.model_dump_json())

    for request_number in count(1):
        try:
            command = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if command == "quit":
            return
        if not command:
            continue
        if command == "restart":
            observation = session.restart()
        else:
            if command in DIRECTIONS:
                action = {"type": "move", "direction": DIRECTIONS[command]}
            else:
                try:
                    action = json.loads(command)
                except json.JSONDecodeError:
                    print("Enter a direction or a valid JSON action object.")
                    continue
            result = session.submit({
                "request_id": f"cli-{request_number}",
                "expected_turn": observation.turn,
                "action": action,
            })
            print(result.model_dump_json())
            observation = session.observation()
        print(observation.model_dump_json())


if __name__ == "__main__":
    main()
