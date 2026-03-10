import { assertContractShape } from "@/lib/contracts";

const STREAM_HEADERS = {
  Accept: "text/event-stream",
  "Content-Type": "application/json",
};

export async function apiPostEventStream(path, payload, options = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: STREAM_HEADERS,
    cache: "no-store",
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `request failed: ${response.status}`);
  }
  if (!response.body || !response.body.getReader) {
    throw new Error("Streaming is not supported in this environment.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const onEvent = options.onEvent || (() => {});
  let remainder = "";
  let lastPayload = null;

  while (true) {
    const { done, value } = await reader.read();
    remainder += decoder.decode(value || new Uint8Array(), { stream: !done });
    const parsed = parseSseBuffer(remainder);
    remainder = parsed.remainder;
    for (const event of parsed.events) {
      if (options.responseContract) {
        assertContractShape(options.responseContract, event.payload);
      }
      lastPayload = event.payload;
      onEvent(event);
      if (event.payload.event_type === "failed") {
        throw new Error(event.payload.detail || "stream failed");
      }
    }
    if (done) {
      break;
    }
  }
  return lastPayload;
}

export function parseSseBuffer(buffer) {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const chunks = normalized.split("\n\n");
  const remainder = chunks.pop() || "";
  const events = [];
  for (const chunk of chunks) {
    const parsed = parseSseChunk(chunk);
    if (!parsed.data) {
      continue;
    }
    events.push({
      name: parsed.event || "message",
      payload: JSON.parse(parsed.data),
    });
  }
  return { events, remainder };
}

function parseSseChunk(chunk) {
  const lines = chunk.split("\n");
  const event = [];
  const data = [];
  for (const line of lines) {
    if (line.startsWith("event:")) {
      event.push(line.slice(6).trim());
    }
    if (line.startsWith("data:")) {
      data.push(line.slice(5).trim());
    }
  }
  return {
    event: event[0] || null,
    data: data.join("\n"),
  };
}
