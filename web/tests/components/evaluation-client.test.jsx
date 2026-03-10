import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import EvaluationClient from "@/components/evaluation-client";
import {
  evalLaunchFixture,
  evalRunsFixture,
  refreshedEvalRunsFixture,
} from "@/tests/fixtures/api-fixtures";
import { installFetchMock } from "@/tests/support/mock-fetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("EvaluationClient", () => {
  it("launches an evaluation run and refreshes the persisted results", async () => {
    let resultsReadCount = 0;
    const fetchMock = installFetchMock({
      "/api/eval/results": () => {
        resultsReadCount += 1;
        return { payload: { runs: resultsReadCount > 1 ? refreshedEvalRunsFixture : evalRunsFixture } };
      },
      "POST /api/eval/run": ({ init }) => {
        const body = JSON.parse(init.body);
        expect(body.eval_set_id).toBe("manual_eval");
        expect(body.model_variant).toBe("base");
        expect(body.trace_ids).toEqual(["trace_dash_001"]);
        return { payload: evalLaunchFixture };
      },
    });

    render(<EvaluationClient />);

    expect(await screen.findByText("eval_existing_001")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("trace_ids (comma separated)"), "trace_dash_001");
    await userEvent.click(screen.getByRole("button", { name: "运行评测" }));

    await screen.findByText("eval_launch_002");
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/eval/run",
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(screen.getAllByText(/cases 1/).length).toBeGreaterThan(0);
  });
});
