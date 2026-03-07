const JSON_HEADERS = {
  "Content-Type": "application/json",
};

export async function apiGet(path) {
  const response = await fetch(path, {
    headers: JSON_HEADERS,
  });
  return handleResponse(response);
}

export async function apiPost(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  });
  return handleResponse(response);
}

async function handleResponse(response) {
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error((data && data.detail) || `request failed: ${response.status}`);
  }
  return data;
}
