# syntax=docker/dockerfile:1

# ---- Build stage: install dependencies and produce the static bundle ----
FROM node:24-slim AS builder

WORKDIR /app

# Install dependencies from the lockfile first for layer caching.
COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
COPY public ./public
RUN npm run build

# ---- Runtime stage: unprivileged nginx serving the built SPA ----
# The nginx-unprivileged image runs as a non-root user (uid 101) and listens on
# 8080 by default, so there is no build tooling and no root in the final image.
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime

# Replace the default site and install the security-headers snippet it includes.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=5 \
    CMD ["wget", "--quiet", "--tries=1", "--spider", "http://127.0.0.1:8080/healthz"]

CMD ["nginx", "-g", "daemon off;"]
