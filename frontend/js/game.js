import { api, ApiError } from "./api.js";
import { bindControls, labelFor } from "./controls.js";
import { createRenderer } from "./renderer.js";

const $ = (id) => document.getElementById(id);
const storageKey = "agentquest-session";
const history = [];
let sessionId = null;
let pending = null;
let observation = null;
let busy = false;
let disconnected = false;

try {
  const saved = JSON.parse(sessionStorage.getItem(storageKey));
  sessionId = saved?.sessionId ?? null;
  pending = saved?.pending ?? null;
} catch {
  // A restricted browser can still play within the current page.
}

const renderer = createRenderer($("map"));
const showControls = bindControls(submit, $("map"), renderer.tileFromEvent);

function saveSession() {
  try {
    sessionStorage.setItem(storageKey, JSON.stringify({ sessionId, pending }));
  } catch {
    // State remains available for this page.
  }
}

function feedback(message, outcome = "") {
  $("feedback").textContent = message;
  $("feedback").dataset.outcome = outcome;
}

function render() {
  const status = observation?.status;
  const terminal = status === "victory" || status === "defeat";
  const statusLabels = { in_progress: "In progress", victory: "Victory", defeat: "Defeat" };
  $("game-status").textContent = statusLabels[status] ?? (busy ? "Connecting" : "No game");
  $("game-status").dataset.state = status ?? "";
  $("position").textContent = observation ? `[${observation.position.join(", ")}]` : "—";
  $("turn").textContent = observation?.turn ?? "—";
  $("health-value").textContent = observation ? `${observation.health} of 3 health` : "Health unavailable";
  $("health").replaceChildren(...Array.from({ length: 3 }, (_, index) => {
    const heart = document.createElement("span");
    heart.className = index < (observation?.health ?? 0) ? "heart" : "heart empty";
    return heart;
  }));
  const items = observation?.inventory ?? [];
  $("inventory").replaceChildren(...(items.length ? items : [null]).map((item) => {
    const entry = document.createElement("li");
    entry.textContent = item ? labelFor(item) : "Empty";
    if (item) entry.dataset.item = item;
    return entry;
  }));
  $("ending").hidden = !terminal;
  $("ending").dataset.state = status ?? "";
  $("ending-title").textContent = statusLabels[status] ?? "";
  $("ending-message").textContent = status === "victory" ? "You escaped with the treasure." : "Restart to try again.";
  $("new-game").disabled = busy;
  $("restart").disabled = busy || !sessionId || disconnected;
  $("recover").hidden = !disconnected;
  $("recover").disabled = busy;
  showControls(observation, Boolean(observation && !busy && !disconnected && !terminal));
  renderer.render(observation);
}

function showHistory() {
  $("history").replaceChildren(...history.map(({ turn, status, message }) => {
    const entry = document.createElement("li");
    entry.textContent = `Turn ${turn} · ${labelFor(status)} · ${message}`;
    return entry;
  }));
}

function record(result) {
  history.unshift(result);
  history.length = Math.min(history.length, 6);
  showHistory();
  feedback(result.message ?? labelFor(result.status), result.status);
}

async function run(operation) {
  if (busy) return;
  busy = true;
  render();
  try {
    await operation();
    disconnected = false;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404 && sessionId) {
      sessionId = pending = observation = null;
      saveSession();
      history.length = 0;
      showHistory();
      feedback("This session has expired. Start a new game.");
      disconnected = false;
    } else {
      disconnected = true;
      feedback(pending ? "Connection interrupted. Reconnect to check the last action." :
        "Unable to reach the game. Reconnect to refresh.");
    }
  } finally {
    busy = false;
    render();
  }
}

async function synchronize() {
  if (pending) {
    try {
      record(await api.act(sessionId, pending));
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 422) throw error;
      feedback(error.message, "rejected");
    }
    pending = null;
    saveSession();
  }
  observation = (await api.observe(sessionId)).observation;
}

async function newGame() {
  const game = await api.create();
  sessionId = game.session_id;
  observation = game.observation;
  pending = null;
  saveSession();
  history.length = 0;
  showHistory();
  feedback("You enter the Forgotten Vault.");
}

function submit(action) {
  if (busy || disconnected || observation?.status !== "in_progress") return;
  run(async () => {
    pending = { request_id: crypto.randomUUID(), expected_turn: observation.turn, action };
    saveSession();
    await synchronize();
  });
}

$("new-game").addEventListener("click", () => run(newGame));
$("restart").addEventListener("click", () => run(async () => {
  observation = (await api.restart(sessionId)).observation;
  history.length = 0;
  showHistory();
  feedback("The dungeon has been reset.");
}));
$("recover").addEventListener("click", () => run(async () => {
  if (!sessionId) return newGame();
  feedback("Reconnected to the dungeon.");
  await synchronize();
}));

run(async () => {
  if (!sessionId) return newGame();
  feedback("You return to the Forgotten Vault.");
  await synchronize();
});
