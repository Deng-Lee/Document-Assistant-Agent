import { apiGet, apiPost } from "/ui/lib/api.js";
import { renderJson, renderTraceCards } from "/ui/components/renderers.js";

const healthStatus = document.querySelector("#health-status");
const ingestForm = document.querySelector("#ingest-form");
const chatForm = document.querySelector("#chat-form");
const ingestResult = document.querySelector("#ingest-result");
const chatResult = document.querySelector("#chat-result");
const traceList = document.querySelector("#trace-list");
const refreshButton = document.querySelector("#refresh-dashboard");

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  refreshDashboard();
});

function bindEvents() {
  refreshButton.addEventListener("click", refreshDashboard);
  ingestForm.addEventListener("submit", submitIngest);
  chatForm.addEventListener("submit", submitChat);
}

async function refreshDashboard() {
  try {
    const [health, traces] = await Promise.all([apiGet("/api/health"), apiGet("/api/traces")]);
    healthStatus.textContent = health.status;
    traceList.innerHTML = renderTraceCards(traces.traces || []);
  } catch (error) {
    healthStatus.textContent = "offline";
    traceList.innerHTML = `<p class="muted">${error.message}</p>`;
  }
}

async function submitIngest(event) {
  event.preventDefault();
  ingestResult.textContent = "ingesting...";
  try {
    const payload = {
      markdown_text: document.querySelector("#ingest-markdown").value,
      source_path_hint: document.querySelector("#ingest-source-path").value || null,
    };
    const result = await apiPost("/api/ingest/text", payload);
    ingestResult.textContent = renderJson(result);
    await refreshDashboard();
  } catch (error) {
    ingestResult.textContent = error.message;
  }
}

async function submitChat(event) {
  event.preventDefault();
  chatResult.textContent = "thinking...";
  try {
    const conversationId = document.querySelector("#conversation-id").value.trim();
    const payload = {
      user_message: document.querySelector("#chat-message").value,
      conversation_id: conversationId || null,
    };
    const result = await apiPost("/api/chat/turn", payload);
    if (result.conversation_id) {
      document.querySelector("#conversation-id").value = result.conversation_id;
    }
    chatResult.textContent = renderJson(result);
    await refreshDashboard();
  } catch (error) {
    chatResult.textContent = error.message;
  }
}
