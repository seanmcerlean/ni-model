FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY models ./models
COPY data ./data
COPY scripts ./scripts
COPY --from=frontend /build/frontend/dist ./frontend/dist
EXPOSE 8000
CMD ["uvicorn", "src.ni_model.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
