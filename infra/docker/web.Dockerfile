FROM node:24-slim

RUN useradd --create-home --shell /usr/sbin/nologin graphview
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@10.27.0 --activate
COPY .npmrc package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json /app/
COPY apps/web /app/apps/web
COPY packages /app/packages
RUN pnpm install --frozen-lockfile && pnpm --filter @graphview/web build && chown -R graphview:graphview /app
WORKDIR /app/apps/web
USER graphview

CMD ["./node_modules/.bin/vite", "preview", "--host", "0.0.0.0", "--port", "4173"]
