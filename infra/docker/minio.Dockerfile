FROM golang:1.26.5-bookworm AS build
ADD --checksum=sha256:45521908307306e925c98d629e1c17d78c8b72b6ee242b1bfb1409f7d8ee5841 \
    https://codeload.github.com/minio/minio/tar.gz/9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a \
    /tmp/minio.tar.gz
WORKDIR /src
RUN tar --extract --gzip --file=/tmp/minio.tar.gz --strip-components=1 \
    && rm /tmp/minio.tar.gz \
    && go get github.com/apache/thrift@v0.23.0 \
        github.com/buger/jsonparser@v1.1.2 \
        github.com/go-jose/go-jose/v4@v4.1.4 \
        github.com/prometheus/prometheus@v0.311.3 \
        go.opentelemetry.io/otel/sdk@v1.43.0 \
        golang.org/x/crypto@v0.52.0 \
        golang.org/x/net@v0.55.0 \
        google.golang.org/grpc@v1.79.3 \
    && CGO_ENABLED=0 go build -mod=mod -buildvcs=false -trimpath -tags kqueue \
        -ldflags="-s -w -X github.com/minio/minio/cmd.Version=2025-10-15T17-29-55Z -X github.com/minio/minio/cmd.CopyrightYear=2025 -X github.com/minio/minio/cmd.ReleaseTag=RELEASE.2025-10-15T17-29-55Z -X github.com/minio/minio/cmd.CommitID=9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a -X github.com/minio/minio/cmd.ShortCommitID=9e49d5e7a648" \
        -o /out/minio .
COPY infra/docker/minio-healthcheck.go /tmp/minio-healthcheck.go
RUN CGO_ENABLED=0 go build -buildvcs=false -trimpath -ldflags="-s -w" -o /out/minio-healthcheck /tmp/minio-healthcheck.go \
    && mkdir -p /out/graphview-data /out/tmp

FROM alpine:3.24 AS certificates
RUN apk upgrade --no-cache && apk add --no-cache ca-certificates

FROM scratch
COPY --from=certificates /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=build --chmod=0555 /out/minio /usr/bin/minio
COPY --from=build --chmod=0555 /out/minio-healthcheck /usr/bin/minio-healthcheck
COPY --from=build --chown=1000:1000 /out/graphview-data /graphview-data
COPY --from=build --chown=1000:1000 /out/tmp /tmp
ENV HOME=/tmp MINIO_UPDATE=off SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
USER 1000:1000
EXPOSE 9000 9001
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD ["/usr/bin/minio-healthcheck"]
ENTRYPOINT ["/usr/bin/minio"]
