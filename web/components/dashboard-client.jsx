"use client";

import { useEffect, useState, useTransition } from "react";

import JsonCard from "@/components/json-card";
import { apiGet, apiPost, getApiBaseHint } from "@/lib/api";

const DEFAULT_MARKDOWN = `---
type: notes
title: Next Console Note
---

# Demo

This record was written from the Next.js frontend.`;

export default function DashboardClient() {
  const [health, setHealth] = useState({ status: "checking" });
  const [traces, setTraces] = useState([]);
  const [evalRuns, setEvalRuns] = useState([]);
  const [ingestPayload, setIngestPayload] = useState({
    source_path_hint: "next_console.md",
    markdown_text: DEFAULT_MARKDOWN,
  });
  const [ingestResult, setIngestResult] = useState(null);
  const [error, setError] = useState("");
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    void refreshDashboard();
  }, []);

  async function refreshDashboard() {
    try {
      setError("");
      const [healthResponse, tracesResponse, evalResponse] = await Promise.all([
        apiGet("/api/health", { responseContract: "health_response" }),
        apiGet("/api/traces", { responseContract: "traces_list_response" }),
        apiGet("/api/eval/results", { responseContract: "eval_results_response" }),
      ]);
      setHealth(healthResponse);
      setTraces(tracesResponse.traces || []);
      setEvalRuns(evalResponse.runs || []);
    } catch (refreshError) {
      setError(refreshError.message);
      setHealth({ status: "offline" });
    }
  }

  function handleFieldChange(event) {
    const { name, value } = event.target;
    setIngestPayload((current) => ({ ...current, [name]: value }));
  }

  function submitIngest(event) {
    event.preventDefault();
    startTransition(async () => {
      try {
        setError("");
        const result = await apiPost("/api/ingest/text", {
          ...ingestPayload,
          source_path_hint: ingestPayload.source_path_hint || null,
        }, { responseContract: "ingest_text_response" });
        setIngestResult(result);
        await refreshDashboard();
      } catch (submitError) {
        setError(submitError.message);
      }
    });
  }

  return (
    <div className="page-stack">
      <section className="page-hero">
        <p className="eyebrow">Dashboard</p>
        <h2>把前端操作台切到 Next.js。</h2>
        <p className="hero-copy">
          当前前端通过 Next rewrite 对接现有 FastAPI API，无需额外改动后端契约。Backend target:{" "}
          <code>{getApiBaseHint()}</code>
        </p>
        <div className="button-row">
          <div className="status-pill">
            <span className={`status-dot ${health.status === "ok" ? "" : "offline"}`} />
            API {health.status}
          </div>
          <button type="button" className="button-secondary" onClick={() => void refreshDashboard()} disabled={isPending}>
            刷新概览
          </button>
        </div>
        {error ? <p className="helper-text">{error}</p> : null}
      </section>

      <section className="stats-grid">
        <article className="stat-card">
          <p className="section-kicker">Health</p>
          <strong>{health.status}</strong>
          <p className="muted">当前前端调用通过 `/api/*` rewrite 进入后端。</p>
        </article>
        <article className="stat-card">
          <p className="section-kicker">Recent Traces</p>
          <strong>{traces.length}</strong>
          <p className="muted">最近写入的 trace 数量，用于快速判断链路是否活着。</p>
        </article>
        <article className="stat-card">
          <p className="section-kicker">Eval Runs</p>
          <strong>{evalRuns.length}</strong>
          <p className="muted">展示 frozen replay 评测是否已经产生可审计结果。</p>
        </article>
      </section>

      <div className="panel-grid">
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="section-kicker">Ingest</p>
              <h3 className="panel-title">导入 Markdown 文本</h3>
              <p className="panel-copy">沿用既有 `/api/ingest/text` 契约，把文档直接送进当前索引链路。</p>
            </div>
          </div>
          <form className="stack" onSubmit={submitIngest}>
            <label className="field">
              <span className="field-label">source_path_hint</span>
              <input name="source_path_hint" value={ingestPayload.source_path_hint} onChange={handleFieldChange} />
            </label>
            <label className="field">
              <span className="field-label">markdown_text</span>
              <textarea name="markdown_text" value={ingestPayload.markdown_text} onChange={handleFieldChange} rows={14} />
            </label>
            <div className="button-row">
              <button type="submit" className="button-primary" disabled={isPending}>
                {isPending ? "导入中..." : "导入文本"}
              </button>
              <button
                type="button"
                className="button-secondary"
                onClick={() => setIngestPayload({ source_path_hint: "next_console.md", markdown_text: DEFAULT_MARKDOWN })}
                disabled={isPending}
              >
                重置示例
              </button>
            </div>
          </form>
        </section>

        <JsonCard title="最近一次导入结果" value={ingestResult} empty="等待第一次导入。" />
      </div>

      <div className="panel-grid">
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="section-kicker">Recent Traces</p>
              <h3 className="panel-title">最新链路摘要</h3>
            </div>
          </div>
          <div className="trace-list">
            {traces.length === 0 ? (
              <p className="muted">暂无 trace。</p>
            ) : (
              traces.slice(0, 4).map((trace) => (
                <article key={trace.trace_id} className="trace-row">
                  <div>
                    <strong>{trace.trace_id}</strong>
                    <div className="pill-row">
                      <span className="tiny-pill">{trace.domain || "UNKNOWN"}</span>
                      <span className="tiny-pill">{trace.task || "UNKNOWN"}</span>
                      <span className="tiny-pill">validator {String(trace.validator_pass ?? "n/a")}</span>
                    </div>
                  </div>
                </article>
              ))
            )}
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="section-kicker">Evaluation</p>
              <h3 className="panel-title">最近评测运行</h3>
            </div>
          </div>
          <div className="trace-list">
            {evalRuns.length === 0 ? (
              <p className="muted">暂无 eval run。</p>
            ) : (
              evalRuns.slice(0, 4).map((run) => (
                <article key={run.eval_run_id} className="trace-row">
                  <div>
                    <strong>{run.eval_run_id}</strong>
                    <div className="pill-row">
                      <span className="tiny-pill">{run.eval_set_id}</span>
                      <span className="tiny-pill">{run.model_variant}</span>
                      <span className="tiny-pill">{run.run_status}</span>
                    </div>
                  </div>
                </article>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
