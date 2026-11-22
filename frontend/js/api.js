export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = "GET", body } = {}) {
  const response = await fetch(`/api/games${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
    signal: AbortSignal.timeout(8000),
  });
  const data = await response.json().catch(() => null);
  if (response.status === 409 && data?.status === "rejected") return data;
  if (!response.ok || data === null) {
    const message = response.status === 422 ? "The server rejected the action format." : `Request failed (HTTP ${response.status}).`;
    throw new ApiError(response.ok ? 502 : response.status, message);
  }
  return data;
}

export const api = {
  create: () => request("", { method: "POST" }),
  observe: (id) => request(`/${encodeURIComponent(id)}`),
  act: (id, body) => request(`/${encodeURIComponent(id)}/actions`, { method: "POST", body }),
  restart: (id) => request(`/${encodeURIComponent(id)}/restart`, { method: "POST" }),
};
