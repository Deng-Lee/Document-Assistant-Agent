export function renderJson(value) {
  return JSON.stringify(value, null, 2);
}

export function renderTraceCards(items) {
  if (!items || items.length === 0) {
    return '<p class="muted">暂无 trace。</p>';
  }
  return items
    .map(
      (item) => `
        <article class="trace-card">
          <header>
            <strong class="trace-id">${escapeHtml(item.trace_id)}</strong>
            <span>${escapeHtml(item.domain || "UNKNOWN")} / ${escapeHtml(item.task || "UNKNOWN")}</span>
          </header>
          <div class="trace-meta">
            <span>gate: ${escapeHtml(item.gate_label || "n/a")}</span>
            <span>latency: ${escapeHtml(String(item.latency ?? "n/a"))}</span>
            <span>validator: ${escapeHtml(String(item.validator_pass ?? "n/a"))}</span>
          </div>
        </article>
      `,
    )
    .join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
