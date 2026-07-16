FROM clamav/clamav:1.5.3
USER 0:0
RUN apk upgrade --no-cache \
    && sed -i '/^UpdateLogFile[[:space:]]/d' /etc/clamav/freshclam.conf \
    && mkdir -p /opt/clamav-seed /run/clamav \
    && cp -a /var/lib/clamav/. /opt/clamav-seed/ \
    && chown -R 100:101 /opt/clamav-seed /var/lib/clamav /run/clamav
COPY --chmod=0555 infra/docker/graphview-clamav.sh /usr/local/bin/graphview-clamav
USER 100:101
ENTRYPOINT ["graphview-clamav"]
