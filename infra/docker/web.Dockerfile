FROM node:24.4.1-bookworm-slim AS build
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@10.27.0 --activate
COPY .npmrc package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json /app/
COPY apps/web /app/apps/web
COPY packages /app/packages
ARG VITE_GRAPHVIEW_API_BASE_URL=""
ENV VITE_GRAPHVIEW_API_BASE_URL=${VITE_GRAPHVIEW_API_BASE_URL}
RUN pnpm install --frozen-lockfile && pnpm --filter @graphview/web build

FROM nginxinc/nginx-unprivileged:1.29.5-alpine AS runtime
COPY infra/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build --chown=101:101 /app/apps/web/dist /usr/share/nginx/html
USER 101:101
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/healthz"]
