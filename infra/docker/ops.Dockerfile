FROM minio/mc:RELEASE.2025-08-13T08-35-41Z AS mc

FROM postgres:18.1-bookworm
RUN apt-get update && apt-get install --yes --no-install-recommends redis-tools && rm -rf /var/lib/apt/lists/*
RUN groupadd --system --gid 10001 graphview && useradd --system --uid 10001 --gid graphview --home-dir /nonexistent --shell /usr/sbin/nologin graphview
COPY --from=mc /usr/bin/mc /usr/local/bin/mc
COPY --chown=graphview:graphview infra/scripts/graphview-ops.sh /usr/local/bin/graphview-ops
RUN chmod 0555 /usr/local/bin/graphview-ops
ENV HOME=/tmp
USER 10001:10001
ENTRYPOINT ["graphview-ops"]
