import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ChatClient from "@/components/chat-client";
import { chatTurnFixture } from "@/tests/fixtures/api-fixtures";
import { installFetchMock } from "@/tests/support/mock-fetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ChatClient", () => {
  it("submits a chat turn and stores the returned conversation id", async () => {
    installFetchMock({
      "POST /api/chat/turn": ({ init }) => {
        const body = JSON.parse(init.body);
        expect(body.user_message).toContain("龟防");
        return { payload: chatTurnFixture };
      },
    });

    render(<ChatClient />);

    await userEvent.click(screen.getByRole("button", { name: "发送消息" }));

    expect(await screen.findByText(/conv_fixture_001/)).toBeInTheDocument();
    expect(screen.getByDisplayValue("conv_fixture_001")).toBeInTheDocument();
    expect(screen.getByText(/ASK_ORIENTATION_V1/)).toBeInTheDocument();
  });
});
