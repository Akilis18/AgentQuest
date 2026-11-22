import assert from "node:assert/strict";
import { test } from "node:test";
import { openChromium, waitFor } from "./chromium.mjs";

const base = new URL(process.env.AGENTQUEST_URL ?? "http://127.0.0.1:8000/");
const health = await fetch(new URL("/api/health", base), { signal: AbortSignal.timeout(3_000) })
  .catch(() => null);
assert(health?.ok, `Start AgentQuest at ${base.origin} before running browser tests.`);

async function openGame(t) {
  const browser = await openChromium(base.href);
  t.after(browser.close);
  const { evaluate, command } = browser;
  let turn = 0;
  const get = (id) => evaluate((id) => document.getElementById(id).textContent, id);
  const click = (id) => evaluate((id) => document.getElementById(id).click(), id);
  const session = () => evaluate(() => JSON.parse(sessionStorage.getItem("agentquest-session")).sessionId);
  const ready = () => waitFor(() => evaluate((expected) =>
    document.getElementById("turn")?.textContent === String(expected) &&
    !document.getElementById("new-game").disabled, turn), `turn ${turn} to render`);
  await ready();

  async function step(input) {
    await input();
    turn++;
    await ready();
    assert.match(await get("history"), new RegExp(`^Turn ${turn} `));
  }
  const key = (key) => evaluate((key) => {
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
  }, key);
  async function walk(keys) {
    for (const letter of keys) await step(() => key(letter));
  }
  async function act(type, { item, target } = {}) {
    await step(() => evaluate((type, item, target) => {
      const mode = document.getElementById("action-type");
      mode.value = type;
      mode.dispatchEvent(new Event("change"));
      if (item) {
        const select = document.getElementById("item");
        select.value = item;
        if (!select.value) throw new Error("Item is unavailable: " + item);
      }
      if (target !== null) {
        const select = document.getElementById("target");
        select.value = JSON.stringify(target);
        if (!select.value) throw new Error("Target is unavailable: " + target);
      }
      document.getElementById("execute").click();
    }, type, item, target));
  }
  async function mapClick(col, row) {
    const point = await evaluate((col, row) => {
      const bounds = document.getElementById("map").getBoundingClientRect();
      return {
        x: bounds.left + bounds.width * (col + 0.5) / 17,
        y: bounds.top + bounds.height * (row + 0.5) / 13,
      };
    }, col, row);
    for (const type of ["mousePressed", "mouseReleased"]) {
      await command("Input.dispatchMouseEvent", { ...point, type, button: "left", clickCount: 1 });
    }
  }
  const pixel = (x, y) => evaluate((x, y) => Array.from(document.getElementById("map")
    .getContext("2d").getImageData(x * 16 + 8, y * 16 + 8, 1, 1).data), x, y);
  const observe = async () => {
    const response = await fetch(new URL(`/api/games/${await session()}`, base));
    assert.equal(response.status, 200);
    return (await response.json()).observation;
  };
  async function restart(button = "restart") {
    await click(button);
    turn = 0;
    await ready();
    assert.equal(await get("history"), "");
    assert.equal(await get("position"), "[3, 6]");
  }
  async function terminal(status) {
    assert.equal(await get("game-status"), status);
    assert(await evaluate(() => !document.getElementById("ending").hidden &&
      document.getElementById("movement").disabled && document.getElementById("action-fields").disabled));
    await key("ArrowRight");
    assert.equal((await observe()).turn, turn);
  }
  return { evaluate, command, get, click, session, step, key, walk, act, mapClick, pixel, observe, restart, terminal };
}

async function serviceApproach(game, collectToolkit) {
  await game.walk("ddssa");
  if (collectToolkit) await game.act("pickup", { item: "toolkit" });
  await game.walk("a");
  await game.act("pickup", { item: "bronze_key" });
  await game.walk("ddwwddsssd");
  await game.step(() => game.key("ArrowRight"));
  assert.match(await game.get("feedback"), /locked door/);
  await game.act("use_item", { item: "bronze_key", target: "bronze_door" });
  await game.walk("dd");
}

test("Guard Post victory, limited observations, and responsive controls", { timeout: 60_000 }, async (t) => {
  const game = await openGame(t);
  const initial = await game.observe();
  assert.deepEqual(initial.objects.map(({ id }) => id), ["entrance_plaque"]);
  assert.equal(initial.tiles.length, 5);
  assert.deepEqual(Object.keys(initial).sort(), ["health", "inventory", "objects", "position", "status", "tiles", "turn"]);
  const fog = await game.pixel(15, 6);
  const visible = await game.pixel(2, 6);
  assert.notDeepEqual(fog, visible);
  assert.equal(await game.evaluate(() => getComputedStyle(document.querySelector("canvas")).imageRendering), "pixelated");

  await game.command("Emulation.setDeviceMetricsOverride", { width: 1280, height: 880, deviceScaleFactor: 1, mobile: false });
  assert(await game.evaluate(() => document.querySelector(".map-panel").getBoundingClientRect().right <
    document.querySelector(".sidebar").getBoundingClientRect().left));
  await game.command("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  assert(await game.evaluate(() => document.querySelector(".map-panel").getBoundingClientRect().bottom <
    document.querySelector(".controls").getBoundingClientRect().top && document.documentElement.scrollWidth === innerWidth));
  await game.command("Emulation.setDeviceMetricsOverride", { width: 1280, height: 880, deviceScaleFactor: 1, mobile: false });

  await game.mapClick(15, 6);
  assert.equal((await game.observe()).turn, 0);
  await game.step(() => game.mapClick(4, 6));
  assert.equal(await game.get("position"), "[4, 6]");
  await game.act("interact", { target: "entrance_plaque" });
  assert.match(await game.get("feedback"), /plaque reads/);
  await game.act("inspect", { target: [4, 5] });
  assert.equal(await game.get("feedback"), "Wall.");
  await game.walk("d");
  assert.notDeepEqual(await game.pixel(2, 6), visible);
  assert.deepEqual(await game.pixel(15, 6), fog);
  await game.walk("ssaas");
  assert.equal(await game.get("inventory"), "Empty");
  await game.act("pickup", { item: "decoy" });
  assert.equal(await game.get("inventory"), "Decoy");
  await game.walk("wddwwddwwwdd");
  await game.step(() => game.key("ArrowRight"));
  assert.match(await game.get("feedback"), /guard blocks/);
  await game.act("use_item", { item: "decoy", target: "vault_guard" });
  assert.equal(await game.get("inventory"), "Empty");
  await game.walk("ddddsssdd");
  await game.act("pickup", { item: "vault_treasure" });
  await game.walk("aawwwaaaaaasssaaaaaa");
  assert.equal(await game.get("position"), "[1, 6]");
  assert.equal(await game.get("health-value"), "3 of 3 health");
  assert.equal(await game.get("inventory"), "Vault Treasure");
  await game.terminal("Victory");
});

test("Service Tunnel victory, restart, and armed-trap defeat", { timeout: 60_000 }, async (t) => {
  const game = await openGame(t);
  await serviceApproach(game, true);
  await game.act("use_item", { item: "toolkit", target: "pressure_plate" });
  await game.walk("dddwwwdd");
  assert.equal(await game.get("health-value"), "3 of 3 health");
  await game.act("pickup", { item: "vault_treasure" });
  await game.walk("aasssaaaaaawwwaaaaaa");
  assert.deepEqual((await game.observe()).inventory, ["bronze_key", "toolkit", "vault_treasure"]);
  await game.terminal("Victory");
  const first = await game.session();
  await game.restart();
  assert.equal(await game.session(), first);
  assert.equal(await game.get("inventory"), "Empty");
  await serviceApproach(game, false);
  for (const health of [2, 1, 0]) {
    if (health < 2) await game.walk("a");
    await game.walk("d");
    assert.equal(await game.get("health-value"), `${health} of 3 health`);
  }
  await game.terminal("Defeat");
  await game.restart("new-game");
  assert.notEqual(await game.session(), first);
  const oldGame = await fetch(new URL(`/api/games/${first}`, base)).then((response) => response.json());
  assert.equal(oldGame.observation.status, "defeat");
});

test("Rapid clicks, stale turns, and lost action and restart responses", { timeout: 60_000 }, async (t) => {
  const game = await openGame(t);
  await game.evaluate(() => {
    const send = window.fetch.bind(window);
    window.actionBodies = [];
    window.fetch = async (url, options) => {
      const result = await send(url, options);
      if (url.endsWith("/actions")) window.actionBodies.push(options.body);
      if (url.endsWith(window.dropResponseFor ?? "/unused")) {
        window.dropResponseFor = null;
        throw new TypeError("Simulated lost response after the server received the request");
      }
      return result;
    };
  });
  await game.step(() => game.evaluate(() => {
    const east = document.querySelector('[data-direction="east"]');
    east.click();
    east.click();
    east.click();
  }));
  assert.equal(await game.evaluate(() => window.actionBodies.length), 1);
  assert.equal(await game.get("position"), "[4, 6]");

  const sessionId = await game.session();
  const concurrent = await fetch(new URL(`/api/games/${sessionId}/actions`, base), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id: "external", expected_turn: 1, action: { type: "move", direction: "east" } }),
  });
  assert.equal(concurrent.status, 200);
  await game.step(() => game.key("ArrowRight"));
  assert.match(await game.get("feedback"), /Stale expected turn/);
  assert.equal(await game.get("position"), "[5, 6]");

  await game.evaluate(() => { window.dropResponseFor = "/actions"; });
  await game.key("ArrowRight");
  const reconnect = () => waitFor(() => game.evaluate(() =>
    !document.getElementById("recover").hidden && !document.getElementById("recover").disabled), "Reconnect button");
  await reconnect();
  assert.equal((await game.observe()).turn, 3);
  assert.equal(await game.get("turn"), "2");
  await game.step(() => game.click("recover"));
  const attempts = await game.evaluate(() => window.actionBodies);
  assert.equal(attempts.at(-1), attempts.at(-2));
  assert.equal(await game.get("position"), "[6, 6]");
  assert.equal((await game.observe()).turn, 3);

  await game.evaluate(() => { window.dropResponseFor = "/restart"; });
  await game.click("restart");
  await reconnect();
  assert.equal((await game.observe()).turn, 0);
  await game.click("recover");
  await waitFor(async () => (await game.get("turn")) === "0", "restarted observation");
  assert.equal(await game.get("history"), "", "restart must also clear rendered action history");
  assert.equal(await game.session(), sessionId);
  await game.key("ArrowRight");
  await waitFor(async () => (await game.get("turn")) === "1", "first move after recovery");
  assert.equal(await game.get("position"), "[4, 6]");
});
