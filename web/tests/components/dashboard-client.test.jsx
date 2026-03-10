import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import DashboardClient from "@/components/dashboard-client";
import {
  evalRunsFixture,
  healthFixture,
  ingestResultFixture,
  traceSummariesFixture,
} from "@/tests/fixtures/api-fixtures";
import { installFetchMock } from "@/tests/support/mock-fetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DashboardClient", () => {
  it("loads dashboard data and submits the ingest flow with fixture payloads", async () => {
    const fetchMock = installFetchMock({
      "/api/health": { payload: healthFixture },
      "/api/traces": { payload: { traces: traceSummariesFixture } },
      "/api/eval/results": { payload: { runs: evalRunsFixture } },
      "POST /api/ingest/text": ({ init }) => {
        const body = JSON.parse(init.body);
        expect(body.source_path_hint).toBe("next_console.md");
        expect(body.markdown_text).toContain("Next Console Note");
        return { payload: ingestResultFixture };
      },
    });

    render(<DashboardClient />);

    expect(await screen.findByText("API ok")).toBeInTheDocument();
    expect(screen.getByText("trace_dash_001")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "导入文本" }));

    await screen.findByText(/doc_dashboard_ingest/);
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/ingest/text",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });
});
