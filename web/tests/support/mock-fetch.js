import { vi } from "vitest";

export function installFetchMock(routes) {
  const fetchMock = vi.fn(async (input, init = {}) => {
    const method = (init.method || "GET").toUpperCase();
    const path = typeof input === "string" ? input : input.toString();
    const handler = routes[`${method} ${path}`] ?? routes[path];
    if (!handler) {
      throw new Error(`Unhandled fetch: ${method} ${path}`);
    }
    const response = typeof handler === "function" ? await handler({ input, init, method, path }) : handler;
    return createJsonResponse(response.payload ?? response, response.status ?? 200);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function createJsonResponse(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(payload),
  };
}

export function createTextResponse(text, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
  };
}
