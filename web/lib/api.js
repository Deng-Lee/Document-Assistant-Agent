import { assertContractShape } from "@/lib/contracts";

const JSON_HEADERS = {
  Accept: "application/json",
  "Content-Type": "application/json",
};

export function getApiBaseHint() {
  return process.env.NEXT_PUBLIC_API_BASE_URL || process.env.PDA_BACKEND_URL || "http://127.0.0.1:8000";
}

export async function apiGet(path, options = {}) {
  const response = await fetch(path, {
    method: "GET",
    headers: JSON_HEADERS,
    cache: "no-store",
  });
  return handleResponse(response, options.responseContract);
}

export async function apiPost(path, payload, options = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: JSON_HEADERS,
    cache: "no-store",
    body: JSON.stringify(payload),
  });
  return handleResponse(response, options.responseContract);
}

async function handleResponse(response, responseContract) {
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (error) {
      throw new Error(`Invalid JSON response (${response.status}): ${text.slice(0, 160)}`);
    }
  }
  if (!response.ok) {
    throw new Error((data && data.detail) || `request failed: ${response.status}`);
  }
  if (responseContract && data != null) {
    assertContractShape(responseContract, data);
  }
  return data;
}
