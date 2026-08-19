# syntax=docker/dockerfile:1

# ============================================================================
# GuardMatch AI — Rank workspace
#
# Three stages. Dependencies are installed once and cached, the application is
# built against them, and the runtime stage receives only what `output:
# "standalone"` determined is actually reachable — which is a fraction of
# node_modules. Copying the whole dependency tree instead would multiply the
# image size for code that never runs.
#
# The security posture deliberately matches the API image rather than being the
# weaker half of the pair: non-root, a read-only root filesystem, and no new
# privileges. A stack is only as constrained as its least constrained container.
# ============================================================================

# ---------------------------------------------------------------------------
# Stage 1 — dependencies
# ---------------------------------------------------------------------------
FROM node:22-alpine AS deps

WORKDIR /build

# Manifest and lockfile only, so this layer is rebuilt when dependencies change
# and not when application code does.
COPY package.json package-lock.json ./

# `npm ci` rather than `npm install`: it installs exactly the lockfile and fails
# if the two disagree, so an image cannot quietly be built against versions the
# repository never recorded.
RUN npm ci

# ---------------------------------------------------------------------------
# Stage 2 — build
# ---------------------------------------------------------------------------
FROM node:22-alpine AS builder

WORKDIR /build

ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /build/node_modules ./node_modules
COPY . .

RUN npm run build

# ---------------------------------------------------------------------------
# Stage 3 — runtime
# ---------------------------------------------------------------------------
FROM node:22-alpine AS runtime

# uid 1001 to match the API image. Two containers in one stack running as the
# same known unprivileged id is easier to reason about than two arbitrary ones.
RUN addgroup --system --gid 1001 guardmatch \
    && adduser --system --uid 1001 --ingroup guardmatch guardmatch

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# The standalone bundle carries its own minimal node_modules and server.js.
COPY --from=builder --chown=guardmatch:guardmatch /build/.next/standalone ./
# Static assets are emitted outside the standalone tree and have to be replaced
# alongside it, or every stylesheet and script 404s at runtime.
COPY --from=builder --chown=guardmatch:guardmatch /build/.next/static ./.next/static

USER guardmatch

EXPOSE 3000

# Hits the page itself rather than a dedicated endpoint. For this service,
# "serving the workspace" is the only thing being alive means. Readiness of the
# model is the API's question, and compose already gates on it.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD node -e "require('http').get('http://127.0.0.1:3000/',r=>process.exit(r.statusCode===200?0:1)).on('error',()=>process.exit(1))"

CMD ["node", "server.js"]
