FROM golang:1.26.5-bookworm AS build
RUN CGO_ENABLED=0 go install -trimpath -ldflags="-s -w" go.opentelemetry.io/collector/cmd/builder@v0.156.0
COPY infra/docker/otelcol-builder.yaml /tmp/otelcol-builder.yaml
RUN /go/bin/builder --config=/tmp/otelcol-builder.yaml

FROM alpine:3.24 AS certificates
RUN apk upgrade --no-cache && apk add --no-cache ca-certificates

FROM scratch
COPY --from=certificates /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=build --chmod=0555 /out/otelcol-graphview /otelcol-contrib
COPY --chown=10001:10001 infra/docker/otel-data /var/lib/otel
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
USER 10001:10001
ENTRYPOINT ["/otelcol-contrib"]
