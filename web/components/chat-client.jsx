"use client";

import { useState, useTransition } from "react";

import JsonCard from "@/components/json-card";
import { apiPost } from "@/lib/api";

export default function ChatClient() {
  const [conversationId, setConversationId] = useState("");
  const [message, setMessage] = useState("龟防怎么破解？我总是被人拉回去。");
  const [response, setResponse] = useState(null);
  const [error, setError] = useState("");
  const [isPending, startTransition] = useTransition();

  function submitTurn(event) {
    event.preventDefault();
    startTransition(async () => {
      try {
        setError("");
        const result = await apiPost("/api/chat/turn", {
          conversation_id: conversationId.trim() || null,
          user_message: message,
        });
        setResponse(result);
        if (result.conversation_id) {
          setConversationId(result.conversation_id);
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
          这里直接打 `/api/chat/turn`，保留当前 Orchestrator、BJJ Coach、Literary agent 和 trace 写入链路。
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
                {isPending ? "处理中..." : "发送消息"}
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

        <JsonCard title="最新对话返回" value={response} empty="等待第一次 turn。" />
      </div>
    </div>
  );
}
