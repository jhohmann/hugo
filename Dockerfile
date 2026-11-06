FROM python:3.12-slim AS builder
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
# This application uses local CPU embeddings, not CUDA.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
RUN groupadd --system hugo \
    && useradd --system --gid hugo --create-home --home-dir /home/hugo hugo \
    && mkdir -p /home/hugo/.cache/huggingface \
    && chown -R hugo:hugo /home/hugo
COPY backend/app /app/app
COPY backend/migrations /app/migrations
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/home/hugo/.cache/huggingface
USER hugo
EXPOSE 8000
# Healthchecks belong to the web service; worker/migrate don't serve HTTP.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
