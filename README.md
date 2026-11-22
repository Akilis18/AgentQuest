# AgentQuest

A turn-based pixel-art dungeon adventure in which an AI Agent will eventually select in-game actions. **Current phase: Milestone 1 (manual, deterministic prototype).**

> Stage 5 adds the browser game. The FastAPI endpoints and terminal runner are also available.

## Development setup (Windows PowerShell)

### Prerequisites
- Git (optional but recommended)
- Python 3.11 or 3.12 (recommended)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager
- VS Code (optional)

### Recommended: uv

Open PowerShell in the project folder (the folder containing `pyproject.toml`).

```powershell
# Confirm uv is available
uv --version

# Create a virtual environment using Python 3.11 (uv may install this Python if needed)
uv python install 3.11
uv venv --python 3.11

# Resolve dependency versions and create uv.lock
uv lock

# Install runtime + dev dependencies into .venv
uv sync

# Show installed packages without needing to activate the environment
uv pip list --python .venv\Scripts\python.exe
```

`uv.lock` should be committed to Git after `uv lock`, giving collaborators the same resolved dependency versions. Do not commit `.venv`.

To activate the virtual environment when desired:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks script activation, **you can skip activation entirely** and use `uv run` commands. There is no need to modify execution policy.

### Alternative: standard pip

If `uv` cannot be installed, use an existing Python 3.11/3.12 installation:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If the Python launcher does not have 3.11, use your installed Python's matching version. `requirements.txt` is a manually maintained compatibility file, not a lockfile.

## Running the game and tests

Start the server from the project root and open [the game](http://127.0.0.1:8000/).

```powershell
uv run uvicorn backend.main:app --reload
```

Use the arrow buttons, arrow keys, or WASD to move. In Move mode, you can
also click an adjacent tile. For other actions, choose the action, select an
item or target where needed, and press **Execute action**. Clicking a visible
target on the map can select it. Find the treasure and bring it to the exit.
**Restart** resets the current session. **New game** creates a separate session.
If a connection drops, **Reconnect** checks the last action with its original
request ID before refreshing the current session.

The terminal runner and the test suite can be started separately.

```powershell
uv run python -m backend.cli
uv run pytest -v
```

Type `n`, `e`, `s`, or `w` to move one tile. Enter other actions as JSON,
one per line. The runner prints an action result and the public observation
after each request. Use `restart` to reset the session or `quit` to exit.

```json
{"type":"interact","target":"entrance_plaque"}
{"type":"inspect","target":[4,6]}
{"type":"pickup","item_id":"decoy"}
{"type":"use_item","item_id":"decoy","target":"vault_guard"}
```

If uv cannot access its cache and the existing `.venv` already has the
dependencies, use `uv --no-cache run --no-sync` in place of `uv run`.

## Running the API

Start the server from the project root.

```powershell
uv run uvicorn backend.main:app --reload
```

Open [Swagger UI](http://127.0.0.1:8000/docs), or run these examples from
another PowerShell window.

```powershell
$base = "http://127.0.0.1:8000/api"
Invoke-RestMethod "$base/health"
$game = Invoke-RestMethod -Method Post -Uri "$base/games"
$gameUrl = "$base/games/$($game.session_id)"
$current = Invoke-RestMethod $gameUrl

$payload = @{
    request_id = [guid]::NewGuid().ToString()
    expected_turn = $current.observation.turn
    action = @{ type = "move"; direction = "east" }
} | ConvertTo-Json -Depth 4

Invoke-RestMethod -Method Post -Uri "$gameUrl/actions" -ContentType "application/json" -Body $payload
Invoke-RestMethod $gameUrl
Invoke-RestMethod -Method Post -Uri "$gameUrl/restart"
```

Creation returns HTTP 201. Creation, retrieval, and restart return the session
ID and public observation. Actions return the action result. An applied or
blocked action returns HTTP 200 and consumes one turn. Unknown sessions return
404, malformed action requests return 422, and rejected actions return 409.

For a retry, resend the same request ID, expected turn, and action to receive
the original result. Reusing an ID with changed arguments returns 409.
Restart resets gameplay, exploration memory, and action history. Retry receipts
remain valid for the life of that session, so use fresh IDs for new actions
after a restart. Fetch the current observation before retrying a stale action
as a new request.

Sessions and receipts live in one server process and are lost when it exits
or reloads. Run the MVP with one worker. The API has no authentication or
session expiry.

## Target project structure

```text
agentquest/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── uv.lock                 # Generated by `uv lock`
├── requirements.txt       # Optional pip fallback
├── .gitignore
├── backend/
│   ├── main.py
│   ├── api/
│   │   ├── routes.py
│   │   └── schemas.py
│   ├── engine/
│   │   ├── models.py
│   │   ├── world.py
│   │   ├── actions.py
│   │   ├── rules.py
│   │   ├── observations.py
│   │   └── session.py
│   └── data/forgotten_vault.json
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   ├── js/{api,game,renderer,controls}.js
│   └── assets/sprites/
└── tests/
    ├── test_world.py
    ├── test_actions.py
    ├── test_rules.py
    ├── test_observations.py
    └── test_api.py
```

## Milestone 1 development order

1. Implement typed world and runtime state models.
2. Build a validated Forgotten Vault grid, guaranteeing two distinct routes to the Vault.
3. Implement and test the five deterministic actions and terminal rules.
4. Add FastAPI sessions and a one-action-per-request endpoint.
5. Build Canvas map rendering, action selector and click-to-act controls.
6. Add browser-level manual playthrough tests and stabilize.

## Forgotten Vault

`backend.engine.world.load_world()` loads the 17×13 level and validates area
connections, entity placement, and both routes. The diagram labels each floor
tile by area.

```text
#################
#################
#################
#######GGGGGGG###
#######G#####G###
#######G#####VVV#
#XEEEJJJ#####VVV#
#####S#T#####VVV#
###SSS#T#####T###
###SSS#TTTTTTT###
#################
#################
#################
```

`E` Entrance, `J` Junction, `S` Storage, `G` Guard Post, `T` Service
Tunnel, `V` Vault, `X` Exit, `#` wall.

Storage holds the Bronze Key, Toolkit, and Decoy. The Guard Post requires
the Decoy. The Service Tunnel requires the Bronze Key, and the Toolkit
allows a damage-free crossing of its pressure plate. Both routes reach
the treasure and allow a return to Exit. Use `interact` on the optional
Entrance plaque to read its clue.

## Design commitments

- World definitions are immutable. Each in-memory `GameSession` owns its state, exploration memory, and action history.
- Coordinates use `[x, y]` in JSON, with the origin at the top left and tile lookup as `tiles[y][x]`.
- Each request carries a request ID, expected turn, and one typed action. Applied and blocked results consume a turn. Rejected results preserve the current turn.
- The history records accepted attempts, including blocked actions, with their arguments and results. Restart clears the history and exploration memory.
- Public observations show the current tile and its cardinal neighbors, plus last-seen tiles and objects. Inspection requires current visibility.

- One action per turn; failed but well-formed attempts also consume a turn.
- Four-direction movement; no pathfinding from a single map click.
- Server-authoritative deterministic rules and partial observations.
- Same action contract for manual UI and future LLM tool calls.
- Return to the Exit with the treasure to win.

See [AGENTS.md](AGENTS.md) for the detailed repository instructions for coding agents and collaborators.
