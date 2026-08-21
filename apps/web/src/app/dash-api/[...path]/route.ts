// Same-origin, read-only proxy in front of the bearer-gated FastAPI backend.
//
// Why it exists: every /api/* route requires HAALAND_API_AUTH_TOKEN
// (apps/api/src/haaland/api/security.py), and that token also authorizes
// approving AI-authored code changes. Shipping it to the browser in a
// NEXT_PUBLIC_* variable would put it in the JavaScript bundle, readable by
// anyone who loads the dashboard. Instead the token stays in this container's
// environment and is attached here, server-side.
//
// Why GET only: with no login in front of the dashboard, a proxy that also
// forwarded writes would let any anonymous visitor approve a remediation
// using the injected token. Reads are exposed deliberately — anyone who
// reaches this origin can read incident logs, root causes, and diffs — so
// this belongs behind IAP, a VPN, or a firewall rule, not on an open domain.
// Approve and reject stay first-party API calls made with the caller's own
// bearer token.

import { NextResponse } from "next/server";

// Container-internal by default: the compose network resolves `api`, and the
// API publishes no host port in the production stack.
const API_ORIGIN = process.env.HAALAND_API_URL ?? "http://api:8000";
const API_TOKEN = process.env.HAALAND_API_AUTH_TOKEN;

// Streaming a proxied response is pointless here (every payload is a small
// JSON document or one markdown file) and forces the route into the edge
// runtime's constraints, so responses are buffered.
export const dynamic = "force-dynamic";

function methodNotAllowed(): NextResponse {
  return NextResponse.json(
    {
      detail:
        "this dashboard is read-only — approve, reject, and debug-session " +
        "creation must be sent to /api/* with your own bearer token",
    },
    { status: 405, headers: { Allow: "GET, HEAD" } }
  );
}

async function forward(request: Request, segments: string[]): Promise<Response> {
  const search = new URL(request.url).search;
  const target = `${API_ORIGIN}/api/${segments.map(encodeURIComponent).join("/")}${search}`;

  const headers: Record<string, string> = {
    Accept: request.headers.get("accept") ?? "application/json",
  };
  if (API_TOKEN) headers.Authorization = `Bearer ${API_TOKEN}`;

  let upstream: Response;
  try {
    upstream = await fetch(target, { method: "GET", headers, cache: "no-store" });
  } catch {
    // A connection failure here means the API container is down or renaming,
    // which is an upstream fault, not a bad request from the browser.
    return NextResponse.json({ detail: "the incident API is unreachable" }, { status: 502 });
  }

  // Content-type is preserved because /api/incidents/{ref}/postmortem returns
  // text/markdown when as_markdown=true, and the client branches on it.
  const body = await upstream.arrayBuffer();
  return new NextResponse(body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      "Cache-Control": "no-store",
    },
  });
}

export async function GET(request: Request, context: RouteContext<"/dash-api/[...path]">) {
  const { path } = await context.params;
  return forward(request, path);
}

export const POST = methodNotAllowed;
export const PUT = methodNotAllowed;
export const PATCH = methodNotAllowed;
export const DELETE = methodNotAllowed;
