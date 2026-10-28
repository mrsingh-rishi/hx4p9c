export async function getJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      /* keep the status text */
    }
    throw new Error(typeof detail === "string" ? detail : "Request failed");
  }
  return response.json();
}

export function getDesk(decisionDate, auction) {
  const params = new URLSearchParams({ decision_date: decisionDate, auction });
  return getJson(`/api/desk?${params}`);
}

export function getAccuracy(auction) {
  const params = new URLSearchParams({ auction });
  return getJson(`/api/accuracy?${params}`);
}
