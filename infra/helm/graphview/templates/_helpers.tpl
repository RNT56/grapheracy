{{- define "graphview.runtimeEnv" -}}
- { name: GRAPHVIEW_SECRET_PROVIDER, value: vault }
- name: POSTGRES_PASSWORD
  valueFrom: { secretKeyRef: { name: {{ .Values.runtimeSecretName }}, key: POSTGRES_PASSWORD } }
- name: GRAPHVIEW_DATABASE_URL
  value: {{ printf "postgresql+psycopg://%s:$(POSTGRES_PASSWORD)@%s-postgresql:5432/%s" .Values.database.auth.username .Release.Name .Values.database.auth.database | quote }}
- name: REDIS_PASSWORD
  valueFrom: { secretKeyRef: { name: {{ .Values.runtimeSecretName }}, key: REDIS_PASSWORD } }
- name: ARQ_REDIS_URL
  value: {{ printf "redis://:$(REDIS_PASSWORD)@%s-redis-master:6379/0" .Release.Name | quote }}
- name: GRAPHVIEW_S3_ACCESS_KEY_ID
  valueFrom: { secretKeyRef: { name: {{ .Values.runtimeSecretName }}, key: MINIO_ROOT_USER } }
- name: GRAPHVIEW_S3_SECRET_ACCESS_KEY
  valueFrom: { secretKeyRef: { name: {{ .Values.runtimeSecretName }}, key: MINIO_ROOT_PASSWORD } }
- name: GRAPHVIEW_VAULT_TOKEN
  valueFrom: { secretKeyRef: { name: {{ .Values.runtimeSecretName }}, key: VAULT_DEV_ROOT_TOKEN } }
{{- end -}}
