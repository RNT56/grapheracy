FROM minio/minio:RELEASE.2025-09-07T16-13-09Z
USER 0:0
RUN mkdir -p /graphview-data && chown 1000:1000 /graphview-data
USER 1000:1000
