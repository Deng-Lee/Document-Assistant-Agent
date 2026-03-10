import { afterEach, describe, expect, it, vi } from "vitest";

import { apiGet, apiPost, getApiBaseHint } from "@/lib/api";
import { createJsonResponse, createTextResponse } from "@/tests/support/mock-fetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("web api client", () => {
  it("returns parsed JSON for successful requests", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => createJsonResponse({ status: "ok" })));

    await expect(apiGet("/api/health", { responseContract: "health_response" })).resolves.toEqual({ status: "ok" });
  });

  it("raises backend detail for failed requests", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => createJsonResponse({ detail: "boom" }, 500)));

    await expect(apiPost("/api/chat/turn", { user_message: "test" })).rejects.toThrow("boom");
  });

  it("raises a descriptive error for invalid JSON responses", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => createTextResponse("not-json", 200)));

    await expect(apiGet("/api/health")).rejects.toThrow("Invalid JSON response");
  });

  it("raises a contract mismatch when the response shape drifts", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => createJsonResponse({ ok: true })));

    await expect(apiGet("/api/health", { responseContract: "health_response" })).rejects.toThrow("Contract mismatch");
  });

  it("returns the configured backend hint when no override is present", () => {
    expect(getApiBaseHint()).toBe("http://127.0.0.1:8000");
  });
});
