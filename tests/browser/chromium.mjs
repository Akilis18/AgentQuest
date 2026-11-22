import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, realpath, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

export async function waitFor(check, description) {
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    const result = await check();
    if (result) return result;
    await delay(40);
  }
  throw new Error(`Timed out waiting for ${description}`);
}

export async function openChromium(url) {
  const executable = process.env.AGENTQUEST_CHROME ?? [
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "/usr/bin/chromium",
    "/usr/bin/google-chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  ].find(existsSync);
  if (!executable) throw new Error("Set AGENTQUEST_CHROME to an installed Chromium browser.");
  const tempRoot = await realpath(tmpdir());
  const profile = await mkdtemp(join(tempRoot, "agentquest-browser-"));
  const chrome = spawn(executable, [
    "--headless=new", "--disable-gpu", "--disable-background-networking",
    "--no-first-run", "--remote-debugging-port=0", `--user-data-dir=${profile}`,
    ...(process.env.AGENTQUEST_CHROME_NO_SANDBOX === "1" ? ["--no-sandbox"] : []),
    url,
  ], { windowsHide: true, stdio: "ignore" });
  let launchError;
  chrome.on("error", (error) => { launchError = error; });
  const closed = new Promise((resolve) => chrome.once("close", resolve));
  let socket;

  async function close() {
    socket?.close();
    chrome.kill();
    await closed;
    const resolvedProfile = await realpath(profile);
    if (dirname(resolvedProfile) !== tempRoot) {
      throw new Error("Chromium profile resolved outside the temporary directory.");
    }
    await rm(resolvedProfile, { recursive: true, force: true, maxRetries: 5, retryDelay: 150 });
  }

  try {
    const target = await waitFor(async () => {
      if (launchError) throw launchError;
      if (chrome.exitCode !== null) throw new Error(`Chromium exited with code ${chrome.exitCode}.`);
      try {
        const [port] = (await readFile(join(profile, "DevToolsActivePort"), "utf8")).split(/\r?\n/);
        const targets = await fetch(`http://127.0.0.1:${port}/json/list`, {
          signal: AbortSignal.timeout(1_000),
        }).then((response) => response.json());
        return targets.find((entry) => entry.type === "page");
      } catch {
        return null;
      }
    }, "Chromium DevTools");
    socket = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      socket.addEventListener("open", resolve, { once: true });
      socket.addEventListener("error", reject, { once: true });
    });
  } catch (error) {
    await close();
    throw error;
  }

  let nextId = 0;
  const requests = new Map();
  socket.addEventListener("message", ({ data }) => {
    const { id, result, error } = JSON.parse(data);
    requests.get(id)?.(result, error);
  });
  socket.addEventListener("close", () => {
    for (const complete of requests.values()) complete(null, { message: "Browser disconnected" });
  });
  function command(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++nextId;
      const timeout = setTimeout(() => {
        requests.delete(id);
        reject(new Error(`Browser command timed out: ${method}`));
      }, 10_000);
      requests.set(id, (result, error) => {
        clearTimeout(timeout);
        requests.delete(id);
        if (error) reject(new Error(error.message));
        else resolve(result);
      });
      socket.send(JSON.stringify({ id, method, params }));
    });
  }

  async function evaluate(fn, ...args) {
    const expression = `(${fn})(...JSON.parse(${JSON.stringify(JSON.stringify(args))}))`;
    const reply = await command("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (reply.exceptionDetails) {
      throw new Error(reply.exceptionDetails.exception?.description ?? reply.exceptionDetails.text);
    }
    return reply.result.value;
  }

  return { close, command, evaluate };
}
