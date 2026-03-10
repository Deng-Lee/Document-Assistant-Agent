"use client";

import { useState, useTransition } from "react";

import JsonCard from "@/components/json-card";
import { apiPostEventStream } from "@/lib/chat-stream";

const CHAT_STREAM_CONTRACTS = [
  "chat_stream_started_event",
  "chat_stream_progress_event",
  "chat_stream_completed_event",
  "chat_stream_failed_event",
];

export default function ChatClient() {
  const [conversationId, setConversationId] = useState("");
  const [message, setMessage] = useState("龟防怎么破解？我总是被人拉回去。");
  const [response, setResponse] = useState(null);
  const [streamEvents, setStreamEvents] = useState([]);
  const [error, setError] = useState("");
  const [isPending, startTransition] = useTransition();

  function submitTurn(event) {
    event.preventDefault();
    startTransition(async () => {
      try {
        setError("");
        setResponse(null);
        setStreamEvents([]);
        const result = await apiPostEventStream("/api/chat/stream", {
          conversation_id: conversationId.trim() || null,
          user_message: message,
        }, {
          responseContract: CHAT_STREAM_CONTRACTS,
          onEvent: ({ payload }) => {
            setStreamEvents((current) => [...current, payload]);
            if (payload.conversation_id) {
              setConversationId(payload.conversation_id);
            }
            if (payload.event_type === "completed") {
              setResponse(payload.payload);
            }
          },
        });
        if (result?.event_type === "completed") {
          setResponse(result.payload);
        }
      } catch (submitError) {
        setError(submitError.message);
      }
    });
  }

  return (
    <div className="page-stack">
      <section className="page-hero">
        <p className="eyebrow">Chat</p>
        <h2>对话编排与澄清循环。</h2>
        <p className="hero-copy">
          这里通过 `/api/chat/stream` 走 SSE，把 Orchestrator、retrieval、generation 的阶段性状态直接映射到页面上。
        </p>
      </section>

      <div className="panel-grid">
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="section-kicker">Turn</p>
              <h3 className="panel-title">发送消息</h3>
            </div>
          </div>
          <form className="stack" onSubmit={submitTurn}>
            <label className="field">
              <span className="field-label">conversation_id</span>
              <input value={conversationId} onChange={(event) => setConversationId(event.target.value)} placeholder="留空则创建新会话" />
            </label>
            <label className="field">
              <span className="field-label">user_message</span>
              <textarea value={message} onChange={(event) => setMessage(event.target.value)} rows={8} />
            </label>
            <div className="button-row">
              <button type="submit" className="button-primary" disabled={isPending}>
                {isPending ? "流式处理中..." : "流式发送消息"}
              </button>
              <button
                type="button"
                className="button-secondary"
                disabled={isPending}
                onClick={() => {
                  setConversationId("");
                  setMessage("迷宫和镜子有什么联系？");
                }}
              >
                切换到 Notes 示例
              </button>
            </div>
            {error ? <p className="helper-text">{error}</p> : null}
          </form>
        </section>

        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="section-kicker">Streaming</p>
              <h3 className="panel-title">阶段事件</h3>
            </div>
          </div>
          <div className="stack">
            {streamEvents.length === 0 ? (
              <p className="muted">等待第一次流式 turn。</p>
            ) : (
              streamEvents.map((eventPayload, index) => (
                <article key={`${eventPayload.event_type}-${index}`} className="trace-row">
                  <div>
                    <strong>{eventPayload.event_type}</strong>
                    <div className="pill-row">
                      <span className="tiny-pill">{eventPayload.conversation_id || "pending"}</span>
                      {"stage" in eventPayload ? <span className="tiny-pill">{eventPayload.stage}</span> : null}
                    </div>
                  </div>
                  <p className="muted">
                    {"message" in eventPayload
                      ? eventPayload.message
                      : eventPayload.payload?.response_type || eventPayload.detail}
                  </p>
                </article>
              ))
            )}
          </div>
        </section>

        <JsonCard title="最新对话返回" value={response} empty="等待第一次 turn。" />
      </div>
    </div>
  );
}
