FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000
WORKDIR /app

COPY requirements.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer libreoffice-calc libreoffice-impress \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && useradd --system --uid 10001 --user-group --create-home proofline

COPY --chown=proofline:proofline backend/ ./backend/
COPY --chown=proofline:proofline ["Uebungsdaten Muster Verpackungen/", "./Uebungsdaten Muster Verpackungen/"]
COPY --from=frontend --chown=proofline:proofline /app/frontend/dist/ ./frontend/dist/

USER proofline
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
