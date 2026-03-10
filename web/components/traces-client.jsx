"use client";

import { useDeferredValue, useEffect, useState, useTransition } from "react";

import JsonCard from "@/components/json-card";
import { apiGet, apiPost } from "@/lib/api";

export default function TracesClient() {
  const [traces, setTraces] = useState([]);
  const [selectedTraceId, setSelectedTraceId] = useState("");
  const [traceDetail, setTraceDetail] = useState(null);
  const [replayPayload, setReplayPayload] = useState(null);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [isPending, startTransition] = useTransition();
  const deferredSearch = useDeferredValue(search);

  useEffect(() => {
    void refreshTraces();
  }, []);

  async function refreshTraces() {
    try {
      setError("");
      const payload = await apiGet("/api/traces");
      const nextTraces = payload.traces || [];
      setTraces(nextTraces);
      if (!selectedTraceId && nextTraces[0]) {
        setSelectedTraceId(nextTraces[0].trace_id);
        await loadTrace(nextTraces[0].trace_id);
      }
    } catch (refreshError) {
      setError(refreshError.message);
    }
  }

  async function loadTrace(traceId) {
    try {
      setError("");
      const detail = await apiGet(`/api/traces/${traceId}`);
      setSelectedTraceId(traceId);
      setTraceDetail(detail);
      setReplayPayload(null);
    } catch (detailError) {
      setError(detailError.message);
    }
  }

  function runReplay() {
    if (!selectedTraceId) {
      return;
    }
    startTransition(async () => {
      try {
        setError("");
        const replay = await apiPost(`/api/replay/${selectedTraceId}`, {
          model_variant: "base",
          use_frozen_evidence: true,
          override_generation_config: {},
        });
        setReplayPayload(replay);
      } catch (replayError) {
        setError(replayError.message);
      }
    });
  }

  const filteredTraces = traces.filter((trace) => {
    const haystack = `${trace.trace_id} ${trace.domain || ""} ${trace.task || ""}`.toLowerCase();
    return haystack.includes(deferredSearch.trim().toLowerCase());
  });

  return (
    <div className="page-stack">
      <section className="page-hero">
        <p className="eyebrow">Traces</p>
        <h2>围绕 frozen trace 做 drill-down 和 replay。</h2>
        <p className="hero-copy">
          这里保留最关键的观测动作：按 trace 浏览、查看详情、基于 frozen evidence 直接回放。
        </p>
      </section>

      <div className="split-grid">
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="section-kicker">Registry</p>
              <h3 className="panel-title">Trace 列表</h3>
            </div>
            <button type="button" onClick={() => void refreshTraces()} disabled={isPending}>
              刷新
            </button>
          </div>
          <label className="field">
            <span className="field-label">过滤</span>
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="trace_id / domain / task" />
          </label>
          <div className="trace-list">
            {filteredTraces.length === 0 ? (
              <p className="muted">没有匹配的 trace。</p>
            ) : (
              filteredTraces.map((trace) => (
                <article key={trace.trace_id} className="trace-row">
                  <div>
                    <strong>{trace.trace_id}</strong>
                    <div className="pill-row">
                      <span className="tiny-pill">{trace.domain || "UNKNOWN"}</span>
                      <span className="tiny-pill">{trace.task || "UNKNOWN"}</span>
                      <span className="tiny-pill">gate {trace.gate_label || "n/a"}</span>
                    </div>
                  </div>
                  <button type="button" onClick={() => void loadTrace(trace.trace_id)}>
                    查看详情
                  </button>
                </article>
              ))
            )}
          </div>
        </section>

        <div className="page-stack">
          <section className="panel">
            <div className="panel-head">
              <div>
                <p className="section-kicker">Replay</p>
                <h3 className="panel-title">冻结回放</h3>
              </div>
              <button type="button" onClick={runReplay} disabled={!selectedTraceId || isPending}>
                {isPending ? "回放中..." : "运行 replay"}
              </button>
            </div>
            <p className="muted">当前选择：{selectedTraceId || "尚未选择 trace"}</p>
            {error ? <p className="helper-text">{error}</p> : null}
          </section>
          <JsonCard title="Trace 详情" value={traceDetail} empty="请选择左侧 trace。" />
          <JsonCard title="Replay 结果" value={replayPayload} empty="点击上方按钮运行 frozen replay。" />
        </div>
      </div>
    </div>
  );
}
