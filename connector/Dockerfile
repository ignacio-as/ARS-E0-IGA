FROM python:3.11-slim

WORKDIR /app

COPY connector/requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY connector .

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD test -f /tmp/connector-ready || exit 1

CMD ["python", "observer.py"]

