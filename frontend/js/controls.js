const directions = {
  ArrowUp: "north", w: "north",
  ArrowLeft: "west", a: "west",
  ArrowDown: "south", s: "south",
  ArrowRight: "east", d: "east",
};

const offsets = {
  north: [0, -1], west: [-1, 0], south: [0, 1], east: [1, 0],
};

const sameTile = (a, b) => a[0] === b[0] && a[1] === b[1];
export const labelFor = (id) => id.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

function fillOptions(select, options, emptyLabel) {
  const previous = select.value;
  select.replaceChildren(...options.map(({ value, label }) => new Option(label, value)));
  if (options.some(({ value }) => value === previous)) select.value = previous;
  if (!options.length) select.add(new Option(emptyLabel, ""));
  select.disabled = !options.length;
}

export function bindControls(send, canvas, tileFromEvent) {
  const actionType = document.querySelector("#action-type");
  const target = document.querySelector("#target");
  const item = document.querySelector("#item");
  const execute = document.querySelector("#execute");
  let observation;
  let active = false;
  let targets = [];

  function render(nextObservation, enabled) {
    observation = nextObservation;
    active = enabled;
    const mode = actionType.value;
    const visibleTiles = observation?.tiles.filter((tile) => tile.visible) ?? [];
    const visiblePositions = new Set(visibleTiles.map((tile) => tile.position.join(",")));
    const objects = observation?.objects.filter((object) => visiblePositions.has(object.position.join(","))) ?? [];
    const inventory = observation?.inventory ?? [];
    const pickups = objects.filter((object) => object.kind === "item" && sameTile(object.position, observation.position));
    const items = mode === "pickup" ? pickups.map((object) => object.id) : inventory;

    targets = objects.filter((object) => {
      if (mode === "inspect") return true;
      if (mode === "interact") return object.kind === "interactable";
      return mode === "use_item" && ["door", "guard", "trap"].includes(object.kind);
    }).map((object) => ({ value: object.id, label: labelFor(object.id), position: object.position }));
    if (mode === "inspect") {
      targets.push(...visibleTiles.map(({ position }) => ({ value: position, position, label: `Tile [${position.join(", ")}]` })));
    }
    fillOptions(item, items.map((id) => ({ value: id, label: labelFor(id) })), mode === "pickup" ? "No item on this tile" : "Inventory is empty");
    fillOptions(target, targets.map(({ value, label }) => ({ value: JSON.stringify(value), label })), "No visible target");

    const needsItem = mode === "pickup" || mode === "use_item";
    const needsTarget = mode !== "move" && mode !== "pickup";
    document.querySelector("#item-field").hidden = !needsItem;
    document.querySelector("#target-field").hidden = !needsTarget;
    document.querySelector("#movement").disabled = !active;
    document.querySelector("#action-fields").disabled = !active;
    canvas.dataset.active = active;
    execute.hidden = mode === "move";
    execute.disabled = (needsItem && !item.value) || (needsTarget && !target.value);
  }

  function move(direction) {
    if (active) send({ type: "move", direction });
  }

  document.querySelector("#movement").addEventListener("click", (event) => {
    const button = event.target.closest("[data-direction]");
    if (button) move(button.dataset.direction);
  });
  document.addEventListener("keydown", (event) => {
    if (!active || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey ||
        event.target.closest("input, select, textarea, [contenteditable]")) return;
    const direction = directions[event.key] ?? directions[event.key.toLowerCase()];
    if (!direction) return;
    event.preventDefault();
    if (!event.repeat) move(direction);
  });
  actionType.addEventListener("change", () => render(observation, active));
  document.querySelector("#action-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!active || execute.disabled || execute.hidden) return;
    const action = { type: actionType.value };
    if (!item.closest("[hidden]")) action.item_id = item.value;
    if (!target.closest("[hidden]")) action.target = JSON.parse(target.value);
    send(action);
  });
  canvas.addEventListener("click", (event) => {
    if (!active) return;
    const selected = tileFromEvent(event);
    const [x, y] = observation.position;
    if (actionType.value === "move") {
      const direction = Object.entries(offsets).find(([, [dx, dy]]) => sameTile(selected, [x + dx, y + dy]));
      if (direction) move(direction[0]);
    } else {
      const match = targets.find((entry) => sameTile(selected, entry.position));
      if (match) target.value = JSON.stringify(match.value);
    }
  });
  return render;
}
