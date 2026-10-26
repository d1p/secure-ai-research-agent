# LiteLLM with OpenTelemetry support.
# The upstream image ships without the optional OTel SDK packages (and with no
# pip in its uv-managed venv); bootstrap pip and install the OTLP HTTP exporter
# (no grpcio needed) so `callbacks: ["otel"]` can export traces straight to
# Tempo.
FROM ghcr.io/berriai/litellm:v1.106.4

RUN /app/.venv/bin/python -m ensurepip --upgrade \
    && /app/.venv/bin/python -m pip install --no-cache-dir \
        opentelemetry-sdk==1.45.0 \
        opentelemetry-exporter-otlp-proto-http==1.45.0
