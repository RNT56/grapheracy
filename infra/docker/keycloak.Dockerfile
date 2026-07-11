FROM scratch AS security-patches
ADD --checksum=sha256:3888e9e69ab66fbacaacc9aea0e9ffbf15368288e4aca468b024dba11c09fbf9 \
    https://repo1.maven.org/maven2/com/fasterxml/jackson/core/jackson-databind/2.21.4/jackson-databind-2.21.4.jar \
    /jackson-databind.jar
ADD --checksum=sha256:e36f5237c1267983e5b88dc2169f6b9d7e50eceec6dc1ca31018e3877e14af66 \
    https://repo1.maven.org/maven2/com/microsoft/sqlserver/mssql-jdbc/13.4.0.jre11/mssql-jdbc-13.4.0.jre11.jar \
    /mssql-jdbc.jar

FROM quay.io/keycloak/keycloak:26.7.0 AS builder
ENV KC_DB=postgres \
    KC_HEALTH_ENABLED=true \
    KC_METRICS_ENABLED=true \
    KC_HTTP_RELATIVE_PATH=/identity
COPY --from=security-patches --chown=1000:0 /jackson-databind.jar /opt/keycloak/lib/lib/main/com.fasterxml.jackson.core.jackson-databind-2.21.2.jar
COPY --from=security-patches --chown=1000:0 /mssql-jdbc.jar /opt/keycloak/lib/lib/main/com.microsoft.sqlserver.mssql-jdbc-13.2.1.jre11.jar
RUN /opt/keycloak/bin/kc.sh build \
    && rm -f /opt/keycloak/bin/client/keycloak-admin-cli-*.jar

FROM quay.io/keycloak/keycloak:26.7.0
COPY --from=builder --chown=1000:0 /opt/keycloak/ /opt/keycloak/
RUN rm -f /opt/keycloak/bin/client/keycloak-admin-cli-*.jar
ENV KC_DB=postgres \
    KC_HEALTH_ENABLED=true \
    KC_METRICS_ENABLED=true \
    KC_HTTP_RELATIVE_PATH=/identity
USER 1000:0
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
CMD ["start", "--optimized"]
