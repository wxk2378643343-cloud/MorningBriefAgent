const LOCAL_API_BASE = "http://127.0.0.1:8765";

export async function probeLocalApi(timeoutMs = 1200) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${LOCAL_API_BASE}/api/v1/health`, {
      signal: controller.signal,
      cache: "no-store",
    });
    if (!response.ok) throw new Error("health check failed");
    return await response.json();
  } finally {
    window.clearTimeout(timer);
  }
}

export function apiUrl(path) {
  return `${LOCAL_API_BASE}${path}`;
}
