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
    if (response && typeof response.text === "function") {
      return response;
    }
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

export function createSseResponse(events, status = 200) {
  const encoded = events.map((event) => {
    const payload = typeof event === "string" ? event : JSON.stringify(event);
    return `data: ${payload}\n\n`;
  }).join("");
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(encoded));
      controller.close();
    },
  });
  return {
    ok: status >= 200 && status < 300,
    status,
    body,
    text: async () => encoded,
  };
}
