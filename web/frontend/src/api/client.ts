/** Shared API transport. Auth token is process-local browser memory only. */

const BASE = ""; // Vite proxy handles /api -> localhost:8501
let bearerToken = "";

export function setAuthToken(token: string) {
  bearerToken = token.trim();
}

export function clearAuthToken() {
  bearerToken = "";
}

export function hasAuthToken(): boolean {
  return bearerToken.length > 0;
}

function authHeaders(): Record<string, string> {
  return bearerToken ? { Authorization: `Bearer ${bearerToken}` } : {};
}

async function req<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(BASE + url, {
    ...opts,
    headers: { "Content-Type": "application/json", ...authHeaders(), ...opts?.headers },
  });
  const contentType = res.headers.get("content-type") || "";
  const bodyText = await res.text().catch(() => "");
  if (!res.ok) {
    if (res.status === 401 || (res.status === 403 && /Invalid API key/i.test(bodyText))) {
      clearAuthToken();
    }
    throw new Error(`[${res.status}] ${bodyText || "Unknown error"}`);
  }
  if (!contentType.includes("application/json")) {
    const hint = contentType.includes("text/html")
      ? "后端路由可能未注册，或本地 API 服务需要重启"
      : "接口未返回 JSON";
    throw new Error(`${hint}: ${url}`);
  }
  return JSON.parse(bodyText) as T;
}

export function get<T>(url: string): Promise<T> {
  return req<T>(url);
}

export function post<T>(url: string, body?: unknown): Promise<T> {
  return req<T>(url, { method: "POST", body: body ? JSON.stringify(body) : undefined });
}

export function put<T>(url: string, body?: unknown): Promise<T> {
  return req<T>(url, { method: "PUT", body: body ? JSON.stringify(body) : undefined });
}

export function patch<T>(url: string, body?: unknown): Promise<T> {
  return req<T>(url, { method: "PATCH", body: body ? JSON.stringify(body) : undefined });
}
