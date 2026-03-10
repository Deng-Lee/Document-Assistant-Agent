"use client";

import { useEffect, useState, useTransition } from "react";

import JsonCard from "@/components/json-card";
import { apiGet, apiPost } from "@/lib/api";

const DEFAULT_FORM = {
  eval_set_id: "manual_eval",
  model_variant: "base",
  trace_ids: "",
};

export default function EvaluationClient() {
  const [form, setForm] = useState(DEFAULT_FORM);
  const [runs, setRuns] = useState([]);
  const [launchPayload, setLaunchPayload] = useState(null);
  const [error, setError] = useState("");
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    void refreshRuns();
  }, []);

  async function refreshRuns() {
    try {
      setError("");
      const payload = await apiGet("/api/eval/results", { responseContract: "eval_results_response" });
      setRuns(payload.runs || []);
    } catch (refreshError) {
      setError(refreshError.message);
    }
  }

  function handleChange(event) {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  }

  function submitRun(event) {
    event.preventDefault();
    startTransition(async () => {
      try {
        setError("");
        const result = await apiPost("/api/eval/run", {
          eval_set_id: form.eval_set_id,
          model_variant: form.model_variant,
          use_frozen_evidence: true,
          trace_ids: form.trace_ids
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
        }, { responseContract: "eval_run_launch_response" });
        setLaunchPayload(result);
        await refreshRuns();
      } catch (submitError) {
        setError(submitError.message);
      }
    });
  }

  return (
    <div className="page-stack">
      <section className="page-hero">
        <p className="eyebrow">Evaluation</p>
        <h2>从前端发起 frozen replay 评测。</h2>
        <p className="hero-copy">
          当前界面直接覆盖 V1 的核心操作：选择 eval set、指定 trace、触发 run，再回看结构化结果。
        </p>
      </section>

      <div className="panel-grid">
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="section-kicker">Launch</p>
              <h3 className="panel-title">启动评测</h3>
            </div>
          </div>
          <form className="stack" onSubmit={submitRun}>
            <label className="field">
              <span className="field-label">eval_set_id</span>
              <input name="eval_set_id" value={form.eval_set_id} onChange={handleChange} />
            </label>
            <label className="field">
              <span className="field-label">model_variant</span>
              <select name="model_variant" value={form.model_variant} onChange={handleChange}>
                <option value="base">base</option>
                <option value="policy">policy</option>
              </select>
            </label>
            <label className="field">
              <span className="field-label">trace_ids (comma separated)</span>
              <textarea name="trace_ids" rows={5} value={form.trace_ids} onChange={handleChange} />
            </label>
            <div className="button-row">
              <button type="submit" className="button-primary" disabled={isPending}>
                {isPending ? "运行中..." : "运行评测"}
              </button>
              <button type="button" className="button-secondary" onClick={() => void refreshRuns()} disabled={isPending}>
                刷新结果
              </button>
            </div>
            {error ? <p className="helper-text">{error}</p> : null}
          </form>
        </section>

        <JsonCard title="最近一次启动结果" value={launchPayload} empty="等待第一次 eval run。" />
      </div>

      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="section-kicker">History</p>
            <h3 className="panel-title">评测历史</h3>
          </div>
        </div>
        <div className="trace-list">
          {runs.length === 0 ? (
            <p className="muted">暂无评测记录。</p>
          ) : (
            runs.map((run) => (
              <article key={run.eval_run_id} className="trace-row">
                <div>
                  <strong>{run.eval_run_id}</strong>
                  <div className="pill-row">
                    <span className="tiny-pill">{run.eval_set_id}</span>
                    <span className="tiny-pill">{run.model_variant}</span>
                    <span className="tiny-pill">{run.run_status}</span>
                    <span className="tiny-pill">cases {run.golden_case_count}</span>
                  </div>
                </div>
              </article>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
