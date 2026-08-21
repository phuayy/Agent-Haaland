// Thin fetch wrapper. Normalizes the two error shapes the backend actually
// produces (see docs/haaland-api-reference.md "Error shapes"): a raised
// HTTPException gives `detail: string`; a Pydantic validation failure gives
// `detail: Array<{ msg: string, loc: unknown[] }>`.

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class HaalandApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "HaalandApiError";
    this.status = status;
  }
}

function detailToMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : JSON.stringify(d)))
      .join("; ");
  }
  return "Request failed";
}

async function handle<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;
  const isJson = res.headers.get("content-type")?.includes("application/json");
  const body = isJson ? await res.json() : await res.text();

  if (!res.ok) {
    const message = isJson && body && typeof body === "object" && "detail" in body
      ? detailToMessage((body as { detail: unknown }).detail)
      : String(body);
    throw new HaalandApiError(res.status, message);
  }

  return body as T;
}

export async function apiGet<T>(path: string, params?: Record<string, string | boolean | undefined>): Promise<T> {
  const url = new URL(path, BASE_URL);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  return handle<T>(res);
}

export async function apiGetText(path: string, params?: Record<string, string | boolean | undefined>): Promise<string> {
  const url = new URL(path, BASE_URL);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }
  const res = await fetch(url);
  if (!res.ok) throw new HaalandApiError(res.status, await res.text());
  return res.text();
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(new URL(path, BASE_URL), {
    method: "POST",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return handle<T>(res);
}

export function apiUrl(path: string, params?: Record<string, string | boolean | undefined>): string {
  const url = new URL(path, BASE_URL);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}
