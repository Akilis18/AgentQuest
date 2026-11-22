import { palette, sprites } from "../assets/sprites/dungeon.js";

const TILE = 16;
const objectSprite = (object) => {
  if (object.kind === "item") return object.item_kind;
  if (object.kind === "interactable") return "plaque";
  if (object.kind === "guard") return object.status === "distracted" ? "distracted" : "guard";
  return object.status;
};

export function createRenderer(canvas) {
  const context = canvas.getContext("2d");
  context.imageSmoothingEnabled = false;

  function rect(color, x, y, width, height) {
    context.fillStyle = color;
    context.fillRect(x, y, width, height);
  }

  function sprite(name, x, y) {
    sprites[name]?.forEach((row, dy) => {
      [...row].forEach((color, dx) => {
        if (palette[color]) rect(palette[color], x + 2 * dx, y + 2 * dy, 2, 2);
      });
    });
  }

  function render(observation) {
    rect("#0d1711", 0, 0, canvas.width, canvas.height);
    for (let y = 0; y < canvas.height; y += TILE) {
      for (let x = 0; x < canvas.width; x += TILE) {
        rect("#18231c", x, y, 1, TILE);
        rect("#18231c", x, y, TILE, 1);
      }
    }
    if (!observation) return;

    const objectsAt = new Map();
    for (const object of observation.objects) {
      const key = object.position.join(",");
      if (!objectsAt.has(key)) objectsAt.set(key, []);
      objectsAt.get(key).push(object);
    }
    for (const tile of observation.tiles) {
      const [col, row] = tile.position;
      const x = col * TILE;
      const y = row * TILE;
      rect("#404d41", x, y, TILE, TILE);
      if (tile.tile === "#") {
        rect("#626f65", x + 1, y + 1, 14, 5);
        rect("#505d54", x + 1, y + 7, 14, 5);
        rect("#394840", x + 6, y + 1, 1, 5);
        rect("#394840", x + 10, y + 7, 1, 5);
        rect("#29382f", x + 1, y + 13, 14, 2);
      } else {
        rect((col + row) % 2 ? "#68735a" : "#636c54", x + 1, y + 1, 15, 15);
        rect("#80896d", x + 3, y + 4, 2, 1);
        rect("#4d5947", x + 10, y + 12, 3, 1);
      }
      if (tile.tile === "E") sprite("exit", x, y);
      for (const object of objectsAt.get(tile.position.join(",")) ?? []) {
        sprite(objectSprite(object), x, y);
      }
      if (!tile.visible) rect("rgba(8, 18, 13, 0.64)", x, y, TILE, TILE);
    }
    const [playerX, playerY] = observation.position.map((coordinate) => coordinate * TILE);
    rect("#ecd382", playerX, playerY + 15, TILE, 1);
    sprite("player", playerX, playerY);
  }

  function tileFromEvent(event) {
    const bounds = canvas.getBoundingClientRect();
    return [
      Math.floor((event.clientX - bounds.left) * canvas.width / bounds.width / TILE),
      Math.floor((event.clientY - bounds.top) * canvas.height / bounds.height / TILE),
    ];
  }

  return { render, tileFromEvent };
}
