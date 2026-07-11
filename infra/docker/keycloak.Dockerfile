FROM scratch AS security-patches
ADD --checksum=sha256:3888e9e69ab66fbacaacc9aea0e9ffbf15368288e4aca468b024dba11c09fbf9 \
    https://repo1.maven.org/maven2/com/fasterxml/jackson/core/jackson-databind/2.21.4/jackson-databind-2.21.4.jar \
    /jackson-databind.jar

FROM quay.io/keycloak/keycloak:26.7.0 AS builder
ENV KC_DB=postgres \
    KC_HEALTH_ENABLED=true \
    KC_METRICS_ENABLED=true \
    KC_HTTP_RELATIVE_PATH=/identity
COPY --from=security-patches --chown=1000:0 /jackson-databind.jar /opt/keycloak/lib/lib/main/com.fasterxml.jackson.core.jackson-databind-2.21.2.jar
RUN rm -f /opt/keycloak/bin/client/keycloak-admin-cli-*.jar \
    /opt/keycloak/lib/lib/main/com.microsoft.sqlserver.mssql-jdbc-*.jar \
    && /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:26.7.0
COPY --from=builder --chown=1000:0 /opt/keycloak/ /opt/keycloak/
RUN rm -f /opt/keycloak/bin/client/keycloak-admin-cli-*.jar \
    /opt/keycloak/lib/lib/main/com.microsoft.sqlserver.mssql-jdbc-*.jar
ENV KC_DB=postgres \
    KC_HEALTH_ENABLED=true \
    KC_METRICS_ENABLED=true \
    KC_HTTP_RELATIVE_PATH=/identity
USER 1000:0
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
CMD ["start", "--optimized"]
