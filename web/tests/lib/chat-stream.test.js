import { describe, expect, it } from "vitest";

import { parseSseBuffer } from "@/lib/chat-stream";

describe("parseSseBuffer", () => {
  it("parses complete SSE chunks and preserves an incomplete remainder", () => {
    const source = [
      'event: started\ndata: {"event_type":"started","conversation_id":"conv_1","message":"accepted"}',
      'event: progress\ndata: {"event_type":"progress","conversation_id":"conv_1","stage":"retrieval","message":"evidence_items=3"}',
      'event: completed\ndata: {"event_type":"completed","conversation_id":"conv_1","payload":{"response_type":"clarify_request"}}',
    ].join("\n\n") + "\n\npartial";

    const parsed = parseSseBuffer(source);

    expect(parsed.events).toHaveLength(3);
    expect(parsed.events[0].name).toBe("started");
    expect(parsed.events[1].payload.stage).toBe("retrieval");
    expect(parsed.events[2].payload.payload.response_type).toBe("clarify_request");
    expect(parsed.remainder).toBe("partial");
  });
});
