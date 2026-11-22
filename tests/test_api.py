from asyncio import gather
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import create_app


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as test_client:
        yield test_client


async def create_game(client):
    response = await client.post("/api/games")
    assert response.status_code == 201
    return response.json()


@pytest.fixture
async def game_url(client):
    return f"/api/games/{(await create_game(client))['session_id']}"


def move(request_id, expected_turn=0, direction="east"):
    return {
        "request_id": request_id,
        "expected_turn": expected_turn,
        "action": {"type": "move", "direction": direction},
    }


async def test_health_and_documentation(client):
    assert (await client.get("/api/health")).json() == {"status": "ok"}
    assert (await client.get("/docs")).status_code == 200
    paths = (await client.get("/openapi.json")).json()["paths"]
    assert set(paths) == {
        "/api/health", "/api/games", "/api/games/{session_id}",
        "/api/games/{session_id}/actions", "/api/games/{session_id}/restart",
    }


async def test_serves_frontend_and_keeps_world_data_private(client):
    page = await client.get("/")
    assert page.status_code == 200
    assert '<canvas id="map"' in page.text
    assert 'src="/js/game.js"' in page.text
    for asset in ("css/style.css", "js/api.js", "js/game.js", "js/controls.js",
                  "js/renderer.js", "assets/sprites/dungeon.js"):
        assert (await client.get(f"/{asset}")).status_code == 200
    assert (await client.get("/backend/data/forgotten_vault.json")).status_code == 404


async def test_create_and_retrieve_game(client):
    start = await create_game(client)
    assert UUID(start["session_id"]).version == 4
    assert start["observation"]["position"] == [3, 6]
    assert start["observation"]["turn"] == 0
    assert start["observation"]["health"] == 3
    response = await client.get(f"/api/games/{start['session_id']}")
    assert response.status_code == 200
    assert response.json() == start


@pytest.mark.parametrize(("method", "suffix"), [
    ("GET", ""), ("POST", "/actions"), ("POST", "/restart"),
])
async def test_unknown_session(client, method, suffix):
    kwargs = {"json": move("unknown")} if suffix == "/actions" else {}
    response = await client.request(method, "/api/games/missing" + suffix, **kwargs)
    assert response.status_code == 404
    assert response.json() == {"detail": "Game session not found."}


async def test_applied_and_blocked_actions(client, game_url):
    applied = await client.post(game_url + "/actions", json=move("step"))
    assert applied.status_code == 200
    assert applied.json() == {
        "request_id": "step", "status": "applied", "turn": 1, "message": "Moved one tile.",
    }
    blocked = await client.post(game_url + "/actions", json=move("wall", 1, "north"))
    assert blocked.status_code == 200
    assert (blocked.json()["status"], blocked.json()["turn"]) == ("blocked", 2)
    observation = (await client.get(game_url)).json()["observation"]
    assert (observation["position"], observation["turn"]) == ([4, 6], 2)


@pytest.mark.parametrize("payload", [
    {"action": {"type": "move", "direction": "east"}},
    move("bad", direction="northeast"),
    move("bad", expected_turn="0"),
    move("bad") | {"action": [{"type": "move", "direction": "east"}]},
])
async def test_malformed_requests_are_rejected(client, game_url, payload):
    start = (await client.get(game_url)).json()
    assert (await client.post(game_url + "/actions", json=payload)).status_code == 422
    assert (await client.get(game_url)).json() == start


async def test_invalid_json_does_not_reserve_a_request_id_or_consume_a_turn(client, game_url):
    malformed = await client.post(
        game_url + "/actions",
        content='{"request_id":"retry",',
        headers={"Content-Type": "application/json"},
    )
    assert malformed.status_code == 422
    assert (await client.get(game_url)).json()["observation"]["turn"] == 0
    valid = await client.post(game_url + "/actions", json=move("retry"))
    assert valid.status_code == 200
    assert valid.json()["turn"] == 1


async def test_stale_turn_conflict_is_idempotent(client, game_url):
    stale = move("stale", 1)
    rejected = await client.post(game_url + "/actions", json=stale)
    assert rejected.status_code == 409
    assert (rejected.json()["status"], rejected.json()["turn"]) == ("rejected", 0)
    assert rejected.json()["message"] == "Stale expected turn."
    assert (await client.post(game_url + "/actions", json=move("current"))).status_code == 200
    # The original expected turn now matches, but retrying preserves the original result.
    retry = await client.post(game_url + "/actions", json=stale)
    assert retry.status_code == 409
    assert retry.json() == rejected.json()
    assert (await client.get(game_url)).json()["observation"]["turn"] == 1


@pytest.mark.parametrize(("direction", "outcome"), [("east", "applied"), ("north", "blocked")])
async def test_duplicate_matches_original_result(client, game_url, direction, outcome):
    payload = move("repeat", direction=direction)
    first = await client.post(game_url + "/actions", json=payload)
    assert first.status_code == 200
    assert first.json()["status"] == outcome
    assert (await client.post(game_url + "/actions", json=move("next", 1))).status_code == 200
    retry = await client.post(game_url + "/actions", json=payload)
    assert retry.status_code == 200
    assert retry.json() == first.json()
    assert (await client.get(game_url)).json()["observation"]["turn"] == 2


@pytest.mark.parametrize("changed", [move("repeat", 1), move("repeat", 0, "west")])
async def test_conflicting_duplicate_id_is_rejected(client, game_url, changed):
    await client.post(game_url + "/actions", json=move("repeat"))
    before = (await client.get(game_url)).json()
    conflict = await client.post(game_url + "/actions", json=changed)
    assert conflict.status_code == 409
    assert conflict.json()["message"] == "Duplicate request ID."
    assert (await client.get(game_url)).json() == before


async def test_sessions_are_independent(client):
    first, second = await create_game(client), await create_game(client)
    assert first["session_id"] != second["session_id"]
    first_url, second_url = [f"/api/games/{game['session_id']}" for game in (first, second)]
    assert (await client.post(first_url + "/actions", json=move("shared-id"))).status_code == 200
    assert (await client.get(second_url)).json() == second
    assert (await client.post(second_url + "/actions", json=move("shared-id"))).status_code == 200


async def test_restart_resets_state_and_history_but_preserves_retry_receipts(client, game_url, app):
    start = (await client.get(game_url)).json()
    original = await client.post(game_url + "/actions", json=move("before"))
    assert (await client.get(game_url)).json() != start
    restarted = await client.post(game_url + "/restart")
    assert restarted.status_code == 200
    assert restarted.json() == start
    session = app.state.games.get(start["session_id"])
    assert session.history() == ()
    assert (await client.post(game_url + "/actions", json=move("before"))).json() == original.json()
    assert (await client.get(game_url)).json() == start
    assert (await client.post(game_url + "/actions", json=move("after"))).status_code == 200


async def test_terminal_rejection_after_playing_through_the_api(client, game_url):
    directions = {"n": "north", "s": "south", "e": "east", "w": "west"}
    actions = [
        *"eesswws",
        {"type": "pickup", "item_id": "decoy"},
        *"neenneennnee",
        {"type": "use_item", "item_id": "decoy", "target": "vault_guard"},
        *"eeeesssee",
        {"type": "pickup", "item_id": "vault_treasure"},
        *"wwnnnwwwwwwssswwwwww",
    ]
    for turn, action in enumerate(actions):
        body = move(f"req-{turn}", turn, directions[action]) if isinstance(action, str) else {
            "request_id": f"req-{turn}", "expected_turn": turn, "action": action,
        }
        response = await client.post(game_url + "/actions", json=body)
        assert response.status_code == 200
        assert response.json()["status"] == "applied"

    completed = (await client.get(game_url)).json()
    assert completed["observation"]["status"] == "victory"
    assert completed["observation"]["position"] == [1, 6]
    rejected = await client.post(game_url + "/actions", json=move("terminal", len(actions)))
    assert rejected.status_code == 409
    assert rejected.json()["turn"] == len(actions)
    assert (await client.get(game_url)).json() == completed


async def test_observation_exposes_only_discovered_tiles_and_objects(client, game_url):
    response = (await client.get(game_url)).json()
    assert set(response) == {"session_id", "observation"}
    observed = response["observation"]
    assert set(observed) == {"position", "health", "turn", "status", "inventory", "tiles", "objects"}
    assert {tuple(tile["position"]) for tile in observed["tiles"]} == {
        (3, 6), (3, 5), (3, 7), (2, 6), (4, 6),
    }
    assert [obj["id"] for obj in observed["objects"]] == ["entrance_plaque"]
    inspect = {
        "request_id": "inspect",
        "expected_turn": 0,
        "action": {"type": "inspect", "target": "vault_treasure"},
    }
    blocked = await client.post(game_url + "/actions", json=inspect)
    assert blocked.json()["status"] == "blocked"
    assert "vault_treasure" not in blocked.text


@pytest.mark.parametrize("same_id", [True, False])
async def test_concurrent_actions_execute_one_turn(client, game_url, same_id):
    first, second = await gather(
        client.post(game_url + "/actions", json=move("first")),
        client.post(game_url + "/actions", json=move("first" if same_id else "second")),
    )

    assert sorted((first.status_code, second.status_code)) == [200, 200 if same_id else 409]
    if same_id:
        assert first.json() == second.json()
    observed = (await client.get(game_url)).json()["observation"]
    assert (observed["turn"], observed["position"]) == (1, [4, 6])
