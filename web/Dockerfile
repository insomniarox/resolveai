FROM node:24-slim

WORKDIR /app

# package.json pins pnpm 11.21.0, and Corepack activates that package manager.
RUN corepack enable

# Install the locked dependency graph before copying source so ordinary source
# edits can reuse the dependency layer.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

# Next.js evaluates rewrites during `next build`, so the Compose-internal API
# address must be present while the production application is built.
ARG RESOLVEAI_API_URL=http://127.0.0.1:8000
RUN RESOLVEAI_API_URL="${RESOLVEAI_API_URL}" pnpm run build

# EXPOSE documents the container port. Compose publishes it on the host.
EXPOSE 3000

CMD ["pnpm", "run", "start"]
