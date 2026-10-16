FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN python -m pip install --no-cache-dir .
RUN mkdir -p /app/data/operational && chown -R 65532:65532 /app/data

USER 65532:65532
EXPOSE 8000
CMD ["uvicorn", "werms_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

