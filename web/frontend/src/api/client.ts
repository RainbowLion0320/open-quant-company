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

export type SseHandlers = Record<string, (data: string) => void>;

function dispatchSseBlock(block: string, handlers: SseHandlers) {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      data.push(line.slice(5).trimStart());
    }
  }
  const handler = handlers[event];
  if (handler) handler(data.join("\n"));
}

export async function streamSse(
  url: string,
  handlers: SseHandlers,
  options: { signal?: AbortSignal } = {},
): Promise<void> {
  const res = await fetch(BASE + url, {
    headers: authHeaders(),
    signal: options.signal,
  });
  const contentType = res.headers.get("content-type") || "";
  if (!res.ok) {
    const bodyText = await res.text().catch(() => "");
    throw new Error(`[${res.status}] ${bodyText || "Unknown error"}`);
  }
  if (!contentType.includes("text/event-stream")) {
    throw new Error(`接口未返回事件流: ${url}`);
  }
  if (!res.body) {
    throw new Error(`接口不支持流式读取: ${url}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let splitIndex = buffer.indexOf("\n\n");
    while (splitIndex >= 0) {
      const block = buffer.slice(0, splitIndex).trim();
      buffer = buffer.slice(splitIndex + 2);
      if (block) dispatchSseBlock(block, handlers);
      splitIndex = buffer.indexOf("\n\n");
    }
  }
  const tail = buffer.trim();
  if (tail) dispatchSseBlock(tail, handlers);
}
