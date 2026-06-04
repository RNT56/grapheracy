FROM node:24-slim

RUN useradd --create-home --shell /usr/sbin/nologin graphview
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json /app/
COPY apps/web /app/apps/web
COPY packages /app/packages
RUN pnpm install --frozen-lockfile && pnpm --filter @graphview/web build
USER graphview

CMD ["pnpm", "--filter", "@graphview/web", "preview", "--host", "0.0.0.0"]
