# AGENTS.md — AgentQuest Repository Instructions

These instructions apply to all files in this repository. Read them before modifying code.

## Project purpose
AgentQuest is a turn-based, pixel-art dungeon game. The player will eventually command an LLM-powered adventurer, but **Milestone 1 is a fully manual, deterministic game**. Do not add LLM calls, agent frameworks, or external AI services until Milestone 2 is explicitly requested.

## Architecture and technology
- Backend: Python 3.11+, FastAPI and Pydantic; deterministic engine code under `backend/engine/`.
- Frontend: vanilla HTML/CSS/JavaScript with a Canvas 2D pixel-art map, under `frontend/`.
- Level definitions: JSON in `backend/data/`. Runtime game state lives on the server.
- Tests: pytest and FastAPI TestClient. Use `uv` for dependency management.
- Keep engine logic independent of FastAPI and UI. API endpoints translate requests and serialize results; frontend only renders observations and submits actions.

## Gameplay invariants (must not change silently)
1. Each accepted, well-formed game action attempts exactly **one** move/interaction and consumes **one** turn, even when blocked by a game rule. Schema-invalid, duplicate, stale, or failed-transport requests do not consume a turn.
2. Allowed actions: `move`, `inspect`, `pickup`, `use_item`, `interact`. All manual inputs and later LLM tool calls must use the same action contract and engine entry point.
3. Movement is 4-directional, one adjacent tile per action. Coordinates use `[x, y]` (origin top-left), and indexing is `tiles[y][x]`. No diagonals, automatic walking, or teleportation.
4. Interactions: pickup on same tile; inspect only current/visible targets within Manhattan distance 1; use-item/interact on same or adjacent reachable targets. Map clicks must not bypass range checks.
5. The **server is authoritative** for inventory, collision, door state, guard state, traps, damage, turn count, and victory. Never trust client state or LLM-generated outcomes.
6. Partial observability is enforced on the server. Return only visible/discovered locations and objects, never the complete hidden level or private runtime state.
7. Start with 3 health. Entering an armed trap tile costs 1 health. Zero health means defeat. Victory requires entering the Exit tile **while carrying the treasure**.
8. The Forgotten Vault reference level has seven logical areas (Entrance, Junction, Storage, Guard Post, Service Tunnel, Vault, Exit), represented in a validated tile grid. Both guarded/Decoy and locked/Key routes must be independently solvable, without unintended bypasses.
9. Key unlocks matching door and is reusable; Toolkit disarms matching trap and is reusable; Decoy distracts guard and is consumed upon successful use. Items require explicit `pickup` actions.
10. The game stops accepting actions after victory/defeat until restarted. Restart resets game state, exploration memory, and action history.
11. Serialize actions per session. Protect against duplicate/stale requests via request ID and expected-turn checks; never apply an action twice due to retries or double clicks.

## Recommended modules
```
backend/
  main.py
  api/{routes.py,schemas.py}
  engine/{models.py,world.py,actions.py,rules.py,observations.py,session.py}
  data/forgotten_vault.json
frontend/{index.html,css/style.css,js/api.js,js/game.js,js/renderer.js,js/controls.js,assets/sprites/}
tests/{test_world.py,test_actions.py,test_rules.py,test_observations.py,test_api.py}
```
This is the target structure; do not create empty modules or unnecessary abstraction just to match it.

## Development workflow
1. Make the smallest change that satisfies a defined requirement.
2. Add or update tests for rule changes. Test the engine without an API/browser, then test API behavior.
3. Prefer typed data models, explicit action schemas, pure validation helpers, clear game-state transitions, and stable entity IDs.
4. World JSON must be validated for map dimensions, tile codes, object placement, unique IDs, reachability, and at least one winning path. Add checks for both intended routes.
5. Keep frontend CSS and art assets separate from rules. Canvas scaling must preserve crisp pixels (`image-rendering: pixelated`).
6. Run `uv run pytest` after backend changes; report actual test outcomes, not hypothetical ones.
7. If asked for implementation, include concise run instructions and mention what is still incomplete.

## Milestone boundaries
- **M1:** manual deterministic dungeon, API, local web UI, comprehensive tests; no AI.
- **M2:** one-action-per-turn LLM controller using existing action schema, no hidden-state access.
- **M3:** structured observation memory, failure handling, replanning, player guidance.
- **M4+:** UI refinement, optional ASR/VLM, evaluations and presentation.

## Security and quality
- Do not commit `.env`, tokens, virtual environments, caches, or generated secret files.
- Do not introduce external assets without checking license and attribution.
- Avoid modifying unrelated files; document important design changes in README or design docs.
- Never claim a feature works unless it has been implemented and tested.
