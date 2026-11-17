FROM node:24-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 DIRA_DATA_DIR=/app/.data
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY backend ./backend
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev
COPY --from=frontend /build/frontend/dist ./frontend/dist
COPY infra ./infra
COPY media ./media
RUN useradd --create-home dira && mkdir -p /app/.data && chown -R dira:dira /app
USER dira
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=4s CMD /app/.venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["/app/.venv/bin/uvicorn", "dira.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
