import { Incident, Service } from "./types";

export const initialServices: Service[] = [
  {
    id: "svc-api-gateway",
    name: "API Gateway",
    repoUrl: "https://github.com/haaland-io/api-gateway",
    baseBranch: "main",
    ownerTeam: "Team Edge",
    tier: "Tier 1",
    health: "p1",
    lastIncidentId: "INC-2026-0042",
  },
  {
    id: "svc-auth",
    name: "Auth Service",
    repoUrl: "https://github.com/haaland-io/auth-service",
    baseBranch: "main",
    ownerTeam: "Team Identity",
    tier: "Tier 1",
    health: "healthy",
    lastIncidentId: "INC-2026-0038",
  },
  {
    id: "svc-payments",
    name: "Payments Service",
    repoUrl: "https://github.com/haaland-io/payments-service",
    baseBranch: "main",
    ownerTeam: "Team Payments",
    tier: "Tier 1",
    health: "p2",
    lastIncidentId: "INC-2026-0041",
  },
  {
    id: "svc-notifications",
    name: "Notifications Service",
    repoUrl: "https://github.com/haaland-io/notifications-service",
    baseBranch: "main",
    ownerTeam: "Team Growth",
    tier: "Tier 2",
    health: "healthy",
    lastIncidentId: "INC-2026-0031",
  },
  {
    id: "svc-search",
    name: "Search Service",
    repoUrl: "https://github.com/haaland-io/search-service",
    baseBranch: "main",
    ownerTeam: "Team Discovery",
    tier: "Tier 2",
    health: "healthy",
    lastIncidentId: "INC-2026-0022",
  },
  {
    id: "svc-internal-admin",
    name: "Internal Admin Panel",
    repoUrl: "https://github.com/haaland-io/internal-admin",
    baseBranch: "develop",
    ownerTeam: "Team Platform",
    tier: "Tier 3",
    health: "healthy",
    lastIncidentId: "INC-2026-0009",
  },
];

export const initialIncidents: Incident[] = [
  {
    id: "INC-2026-0042",
    serviceId: "svc-api-gateway",
    serviceName: "API Gateway",
    severity: "P1",
    status: "active",
    title: "Database connection pool exhausted under peak load",
    createdAt: "2026-08-17T09:14:00Z",
    graphNodes: [
      { id: "client", label: "Client / CDN", failing: false },
      { id: "svc-api-gateway", label: "API Gateway", failing: true },
      { id: "svc-auth", label: "Auth Service", failing: false },
      { id: "svc-payments", label: "Payments Service", failing: false },
      { id: "db", label: "Postgres Primary", failing: false },
    ],
    graphEdges: [
      { id: "e1", source: "client", target: "svc-api-gateway" },
      { id: "e2", source: "svc-api-gateway", target: "svc-auth" },
      { id: "e3", source: "svc-api-gateway", target: "svc-payments" },
      { id: "e4", source: "svc-auth", target: "db" },
      { id: "e5", source: "svc-payments", target: "db" },
    ],
    logs: `File "/app/haaland/gateway/db/pool.py", line 118, in acquire
    conn = await self._pool.acquire(timeout=self._timeout)
  File "/usr/local/lib/python3.11/site-packages/asyncpg/pool.py", line 827, in acquire
    return await self._acquire(timeout)
  File "/usr/local/lib/python3.11/site-packages/asyncpg/pool.py", line 856, in _acquire
    raise PoolTimeoutError(
asyncpg.exceptions.PoolTimeoutError: pool exhausted, timeout after 5.00s
  (active=100, idle=0, max_size=100)

  File "/app/haaland/gateway/routes/proxy.py", line 44, in forward_request
    async with db_pool.acquire() as conn:
  File "/app/haaland/gateway/middleware/tracing.py", line 29, in __call__
    response = await call_next(request)
fastapi.exceptions.HTTPException: 503 Service Unavailable
  detail="upstream database pool exhausted, 412 requests queued"

WARNING  haaland.gateway.db.pool  pool utilization at 100% for 45s
ERROR    haaland.gateway.routes.proxy  request abc123ef timed out waiting for connection
ERROR    haaland.gateway.routes.proxy  request abc123f0 timed out waiting for connection
CRITICAL haaland.gateway.health  readiness probe failing: db pool saturated`,
    rootCause:
      "A schema migration on Payments Service introduced an unindexed query, causing individual transactions to hold connections 40x longer than baseline. Connection pool (max_size=100) saturated within 3 minutes, starving API Gateway of database access and triggering cascading 503s.",
    remediation:
      "Rolled back Payments Service migration 0027_add_ledger_index to previous revision. Increased API Gateway pool max_size from 100 to 160 as a short-term buffer. Opened follow-up ticket to add the missing composite index (ledger_entries.account_id, created_at) before re-attempting the migration.",
    auditTimeline: [
      { time: "09:14:02", actor: "agent-haaland", action: "Anomaly detected: p99 latency +820% on API Gateway" },
      { time: "09:14:11", actor: "agent-haaland", action: "Correlated spike with deploy payments-service@a91f3c2" },
      { time: "09:14:40", actor: "agent-haaland", action: "Pulled traceback and pool metrics from gateway pods" },
      { time: "09:15:03", actor: "agent-haaland", action: "Root cause hypothesis formed: connection pool exhaustion" },
      { time: "09:15:22", actor: "agent-haaland", action: "Drafted rollback PR #482 for payments-service" },
      { time: "09:16:05", actor: "@sre-team", action: "Rollback PR approved and merged" },
      { time: "09:17:40", actor: "agent-haaland", action: "Monitoring recovery: pool utilization dropping" },
    ],
  },
  {
    id: "INC-2026-0041",
    serviceId: "svc-payments",
    serviceName: "Payments Service",
    severity: "P2",
    status: "active",
    title: "Elevated 5xx rate on /v1/charges after cache deploy",
    createdAt: "2026-08-18T22:41:00Z",
    graphNodes: [
      { id: "svc-api-gateway", label: "API Gateway", failing: false },
      { id: "svc-payments", label: "Payments Service", failing: true },
      { id: "redis", label: "Redis Cache", failing: false },
      { id: "stripe", label: "Stripe API", failing: false },
    ],
    graphEdges: [
      { id: "e1", source: "svc-api-gateway", target: "svc-payments" },
      { id: "e2", source: "svc-payments", target: "redis" },
      { id: "e3", source: "svc-payments", target: "stripe" },
    ],
    logs: `File "/app/haaland/payments/cache/client.py", line 61, in get_idempotency_key
    value = await self._redis.get(key)
  File "/usr/local/lib/python3.11/site-packages/redis/asyncio/client.py", line 542, in get
    return await self.execute_command("GET", name)
redis.exceptions.ConnectionError: Error 111 connecting to redis-cache:6379. Connection refused.

  File "/app/haaland/payments/routes/charges.py", line 88, in create_charge
    idem_key = await cache.get_idempotency_key(request_id)
fastapi.exceptions.HTTPException: 500 Internal Server Error

ERROR    haaland.payments.cache  redis connection refused, 3 retries exhausted
ERROR    haaland.payments.routes.charges  charge request failed: cache unavailable`,
    rootCause:
      "Redis cache deploy rotated credentials without updating the payments-service secret mount, causing all cache calls to fail closed and 5xx on the charge creation path.",
    remediation:
      "Restored previous Redis credentials secret and restarted payments-service pods. Added a pre-deploy check that validates secret mounts against the target cache cluster before rollout.",
    auditTimeline: [
      { time: "22:41:05", actor: "agent-haaland", action: "Anomaly detected: 5xx rate +340% on /v1/charges" },
      { time: "22:41:20", actor: "agent-haaland", action: "Isolated failure to Redis connection errors" },
      { time: "22:42:10", actor: "agent-haaland", action: "Identified credential rotation as likely cause" },
      { time: "22:43:00", actor: "@sre-team", action: "Investigating secret mount configuration" },
    ],
  },
  {
    id: "INC-2026-0038",
    serviceId: "svc-auth",
    serviceName: "Auth Service",
    severity: "P2",
    status: "resolved",
    title: "Token refresh latency spike from expired signing key cache",
    createdAt: "2026-08-10T04:02:00Z",
    resolvedAt: "2026-08-10T04:31:00Z",
    graphNodes: [
      { id: "svc-auth", label: "Auth Service", failing: true },
      { id: "kms", label: "KMS", failing: false },
      { id: "db", label: "Postgres Primary", failing: false },
    ],
    graphEdges: [
      { id: "e1", source: "svc-auth", target: "kms" },
      { id: "e2", source: "svc-auth", target: "db" },
    ],
    logs: `WARNING  haaland.auth.keys  signing key cache stale, refetching from KMS
ERROR    haaland.auth.keys  KMS request latency 4200ms, exceeds 2000ms budget
ERROR    haaland.auth.routes.token  token refresh p99 latency 3800ms`,
    rootCause:
      "Signing key cache TTL expired during a KMS regional latency blip, forcing every token refresh to synchronously fetch keys and blocking on slow KMS responses.",
    remediation:
      "Extended signing key cache TTL from 5m to 30m and added a background refresh job so cache misses no longer block the request path.",
    auditTimeline: [
      { time: "04:02:15", actor: "agent-haaland", action: "Anomaly detected: token refresh p99 +190%" },
      { time: "04:05:40", actor: "agent-haaland", action: "Correlated with KMS regional latency" },
      { time: "04:10:00", actor: "agent-haaland", action: "Deployed cache TTL hotfix" },
      { time: "04:31:00", actor: "agent-haaland", action: "Metrics nominal, incident resolved" },
    ],
  },
  {
    id: "INC-2026-0031",
    serviceId: "svc-notifications",
    serviceName: "Notifications Service",
    severity: "P2",
    status: "resolved",
    title: "Email queue backlog from provider rate limiting",
    createdAt: "2026-07-29T11:00:00Z",
    resolvedAt: "2026-07-29T11:45:00Z",
    graphNodes: [
      { id: "svc-notifications", label: "Notifications Service", failing: true },
      { id: "queue", label: "SQS Queue", failing: false },
      { id: "provider", label: "Email Provider", failing: false },
    ],
    graphEdges: [
      { id: "e1", source: "svc-notifications", target: "queue" },
      { id: "e2", source: "svc-notifications", target: "provider" },
    ],
    logs: `ERROR    haaland.notifications.email  provider rate limit exceeded: 429 Too Many Requests
WARNING  haaland.notifications.queue  backlog depth 14200, growing`,
    rootCause:
      "A marketing campaign burst sent notification volume 6x above the provisioned provider rate limit, causing sustained 429s and queue backlog growth.",
    remediation:
      "Applied exponential backoff with jitter to provider client and requested a temporary rate limit increase from the vendor.",
    auditTimeline: [
      { time: "11:00:30", actor: "agent-haaland", action: "Anomaly detected: queue backlog depth rising" },
      { time: "11:12:00", actor: "agent-haaland", action: "Applied backoff/jitter hotfix" },
      { time: "11:45:00", actor: "agent-haaland", action: "Backlog drained, incident resolved" },
    ],
  },
  {
    id: "INC-2026-0022",
    serviceId: "svc-search",
    serviceName: "Search Service",
    severity: "P2",
    status: "resolved",
    title: "Index rebuild caused temporary relevance degradation",
    createdAt: "2026-07-14T15:20:00Z",
    resolvedAt: "2026-07-14T15:50:00Z",
    graphNodes: [
      { id: "svc-search", label: "Search Service", failing: true },
      { id: "es", label: "Elasticsearch Cluster", failing: false },
    ],
    graphEdges: [{ id: "e1", source: "svc-search", target: "es" }],
    logs: `WARNING  haaland.search.index  rebuild in progress, serving partial shard set
WARNING  haaland.search.relevance  score distribution anomaly detected`,
    rootCause:
      "Scheduled index rebuild overlapped with peak traffic, temporarily serving from a partial shard set and degrading relevance scoring.",
    remediation:
      "Rescheduled index rebuilds to low-traffic windows and added a shard-readiness gate before traffic cutover.",
    auditTimeline: [
      { time: "15:20:10", actor: "agent-haaland", action: "Anomaly detected: relevance score distribution shift" },
      { time: "15:35:00", actor: "agent-haaland", action: "Confirmed correlation with index rebuild job" },
      { time: "15:50:00", actor: "agent-haaland", action: "Rebuild completed, incident resolved" },
    ],
  },
  {
    id: "INC-2026-0009",
    serviceId: "svc-internal-admin",
    serviceName: "Internal Admin Panel",
    severity: "P2",
    status: "resolved",
    title: "Stale build served after CDN cache purge failure",
    createdAt: "2026-06-30T08:00:00Z",
    resolvedAt: "2026-06-30T08:20:00Z",
    graphNodes: [
      { id: "svc-internal-admin", label: "Internal Admin Panel", failing: true },
      { id: "cdn", label: "CDN", failing: false },
    ],
    graphEdges: [{ id: "e1", source: "svc-internal-admin", target: "cdn" }],
    logs: `ERROR    haaland.admin.deploy  cdn purge failed: 502 from edge provider
WARNING  haaland.admin.deploy  serving stale build hash 7f2a1c`,
    rootCause:
      "CDN purge API returned intermittent 502s during deploy, leaving edge nodes serving the previous build.",
    remediation: "Retried purge with backoff and added a purge-verification step to the deploy pipeline.",
    auditTimeline: [
      { time: "08:00:20", actor: "agent-haaland", action: "Anomaly detected: version mismatch across edge nodes" },
      { time: "08:10:00", actor: "agent-haaland", action: "Re-issued CDN purge, verified propagation" },
      { time: "08:20:00", actor: "agent-haaland", action: "All edges consistent, incident resolved" },
    ],
  },
];
