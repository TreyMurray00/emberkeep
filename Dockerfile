# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS web-builder
WORKDIR /build/web
RUN npm install --global pnpm@9.11.0
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000
WORKDIR /app

COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt \
    && addgroup --system emberkeep \
    && adduser --system --ingroup emberkeep --home /app emberkeep

COPY --chown=emberkeep:emberkeep server/ ./server/
COPY --from=web-builder --chown=emberkeep:emberkeep /build/web/dist/client/ ./web/dist/client/

USER emberkeep
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/health',timeout=3)" || exit 1
CMD ["sh", "-c", "exec uvicorn server.app:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
