# Signal Sports web image (#263): the production frontend build served by an
# unprivileged nginx, which also proxies /api and /health to the API service,
# so the browser sees ONE origin (no CORS; CSRF checks the forwarded Origin).
# Build context is frontend/ (frontend/.dockerignore is an allowlist, so a
# developer's .env.local can never change the build). Base images pinned by
# digest; bump them deliberately.
FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Read at build time by Vite. Same-origin API: no VITE_API_BASE_URL.
ENV VITE_DATA_MODE=backend
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.28-alpine@sha256:7377697a821c131a924a7105fafbe7414db4e9fcc77a6f08f776f33f141ec3f8
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
ARG GIT_SHA=unknown
LABEL org.opencontainers.image.title="signal-web" \
      org.opencontainers.image.source="https://github.com/Guy-Navon/signal-sports" \
      org.opencontainers.image.revision="${GIT_SHA}"
# nginx-unprivileged runs as uid 101 and listens on 8080.
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/healthz"]
