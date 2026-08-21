// Thin fetch wrapper. Normalizes the two error shapes the backend actually
// produces (see docs/haaland-api-reference.md "Error shapes"): a raised
// HTTPException gives `detail: string`; a Pydantic validation failure gives
// `detail: Array<{ msg: string, loc: unknown[] }>`.
//
// Two transports, picked by whether NEXT_PUBLIC_API_URL is set at build time:
//
//   set   — direct mode. Calls go straight to that origin, exactly as before.
//           This is local development, where the API runs without
//           HAALAND_API_AUTH_TOKEN and therefore needs no credential.
//
//   unset — proxy mode, which is how the deployed VM builds. Every /api/*
//           path is rewritten to the same-origin /dash-api/* route handler,
//           which attaches the bearer token server-side. The token stays in
//           the web container's environment and never reaches the browser
//           bundle, where anyone loading the page could read it and then call
//           the API directly with approval rights.
//
// Proxy mode is read-only by construction: the route handler forwards GET and
// refuses every write. Callers check READ_ONLY before offering a write action
// rather than letting the 405 surface as a failed request.

const DIRECT_ORIGIN = process.env.NEXT_PUBLIC_API_URL;

/** Proxy mode forwards GET only, so writes are unavailable in this build. */
export const READ_ONLY = !DIRECT_ORIGIN;

const PROXY_PREFIX = "/dash-api";

// Only used to parse and re-serialize relative paths in proxy mode; the host
// is discarded before the value is returned, so it is never requested.
const RELATIVE_BASE = "http://relative.invalid";

export class HaalandApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "HaalandApiError";
    this.status = status;
  }
}

/** Absolute URL in direct mode, same-origin relative path in proxy mode.
 * Relative is deliberate: it avoids reading window.location, which is absent
 * while Next server-renders these client components. */
function resolve(path: string, params?: Record<string, string | boolean | undefined>): string {
  const url = new URL(path, DIRECT_ORIGIN ?? RELATIVE_BASE);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }
  if (DIRECT_ORIGIN) return url.toString();
  return `${PROXY_PREFIX}${url.pathname.replace(/^\/api/, "")}${url.search}`;
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
  const res = await fetch(resolve(path, params), { headers: { Accept: "application/json" } });
  return handle<T>(res);
}

export async function apiGetText(path: string, params?: Record<string, string | boolean | undefined>): Promise<string> {
  const res = await fetch(resolve(path, params));
  if (!res.ok) throw new HaalandApiError(res.status, await res.text());
  return res.text();
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(resolve(path), {
    method: "POST",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return handle<T>(res);
}

export function apiUrl(path: string, params?: Record<string, string | boolean | undefined>): string {
  return resolve(path, params);
}
