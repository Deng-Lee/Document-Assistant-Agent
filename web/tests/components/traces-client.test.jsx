import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import TracesClient from "@/components/traces-client";
import {
  replayResultFixture,
  traceDetailFixture,
  traceSummariesFixture,
} from "@/tests/fixtures/api-fixtures";
import { installFetchMock } from "@/tests/support/mock-fetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TracesClient", () => {
  it("loads trace details and runs replay against frozen evidence", async () => {
    const fetchMock = installFetchMock({
      "/api/traces": { payload: { traces: traceSummariesFixture } },
      "/api/traces/trace_dash_001": { payload: traceDetailFixture },
      "POST /api/replay/trace_dash_001": { payload: replayResultFixture },
    });

    render(<TracesClient />);

    expect(await screen.findByText("trace_dash_001")).toBeInTheDocument();
    await screen.findByText(/mock-bjj-base/);

    await userEvent.click(screen.getByRole("button", { name: "运行 replay" }));

    await screen.findByText(/Keep your elbow inside/);
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/replay/trace_dash_001",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });
});
