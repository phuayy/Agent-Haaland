# Production image for the dashboard. Build context is apps/web:
#
#   docker build -f apps/web/Dockerfile apps/web
#
# The compose file passes that context explicitly; the web app shares no code
# with apps/api, so there is nothing above this directory it needs.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# npm ci, not npm install: the lockfile is the build's input, and a silent
# dependency bump between a local build and the VM's is exactly the drift this
# image exists to avoid.
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* values are inlined at build time, not read at runtime. Leaving
# NEXT_PUBLIC_API_URL unset is what selects proxy mode in lib/api/client.ts —
# the browser then calls /dash-api on this origin and the bearer token stays
# server-side. Setting it here would point browsers straight at the API and
# every request would come back 401.
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Non-root: this container holds HAALAND_API_AUTH_TOKEN in its environment.
RUN addgroup -g 1001 -S nodejs && adduser -u 1001 -S nextjs -G nodejs

COPY --from=builder /app/public ./public
# The standalone output already contains server.js plus its pruned
# node_modules; .next/static is served by it but emitted separately.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
