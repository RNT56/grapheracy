FROM otel/opentelemetry-collector-contrib:0.153.0

COPY --chown=10001:10001 infra/docker/otel-data /var/lib/otel
USER 10001:10001
