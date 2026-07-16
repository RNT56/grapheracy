FROM golang:1.26.5-bookworm AS mc
ADD --checksum=sha256:4cea8ed209c8f96e59ea1a5cc4901019b54c2be6d6f5f16c6749ea8bdcf4172e \
    https://codeload.github.com/minio/mc/tar.gz/d6541ea280b73a834b64d4097e21f2be77676104 \
    /tmp/mc.tar.gz
WORKDIR /src
RUN tar --extract --gzip --file=/tmp/mc.tar.gz --strip-components=1 \
    && rm /tmp/mc.tar.gz \
    && go get github.com/prometheus/prometheus@v0.311.3 \
        golang.org/x/crypto@v0.52.0 \
        golang.org/x/net@v0.55.0 \
        google.golang.org/grpc@v1.79.3 \
    && CGO_ENABLED=0 go build -mod=mod -buildvcs=false -trimpath -tags kqueue \
        -ldflags="-s -w -X github.com/minio/mc/cmd.Version=2025-08-13T08-35-41Z -X github.com/minio/mc/cmd.CopyrightYear=2025 -X github.com/minio/mc/cmd.ReleaseTag=RELEASE.2025-08-13T08-35-41Z -X github.com/minio/mc/cmd.CommitID=d6541ea280b73a834b64d4097e21f2be77676104 -X github.com/minio/mc/cmd.ShortCommitID=d6541ea280b7" \
        -o /out/mc .

FROM postgres:18.4-bookworm
RUN apt-get update \
    && apt-get upgrade --yes \
    && apt-get install --yes --no-install-recommends redis-tools \
    && rm -rf /var/lib/apt/lists/* /usr/local/bin/gosu
RUN groupadd --system --gid 10001 graphview && useradd --system --uid 10001 --gid graphview --home-dir /nonexistent --shell /usr/sbin/nologin graphview
COPY --from=mc /out/mc /usr/local/bin/mc
COPY --chown=graphview:graphview infra/scripts/graphview-ops.sh /usr/local/bin/graphview-ops
RUN chmod 0555 /usr/local/bin/graphview-ops
ENV HOME=/tmp
USER 10001:10001
ENTRYPOINT ["graphview-ops"]
