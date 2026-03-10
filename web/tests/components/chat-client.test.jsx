import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ChatClient from "@/components/chat-client";
import { chatStreamFixture } from "@/tests/fixtures/api-fixtures";
import { createSseResponse, installFetchMock } from "@/tests/support/mock-fetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ChatClient", () => {
  it("submits a streamed chat turn and stores the returned conversation id", async () => {
    installFetchMock({
      "POST /api/chat/stream": ({ init }) => {
        const body = JSON.parse(init.body);
        expect(body.user_message).toContain("龟防");
        return createSseResponse(chatStreamFixture);
      },
    });

    render(<ChatClient />);

    await userEvent.click(screen.getByRole("button", { name: "流式发送消息" }));

    expect(await screen.findByDisplayValue("conv_fixture_001")).toBeInTheDocument();
    expect(screen.getByText(/ASK_ORIENTATION_V1/)).toBeInTheDocument();
    expect(screen.getByText(/next_action=CLARIFY/)).toBeInTheDocument();
  });
});
