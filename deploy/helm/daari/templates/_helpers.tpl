{{- define "daari.fullname" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- /* repository@digest when image.digest is set; otherwise repository:tag. */ -}}
{{- define "daari.image" -}}
{{- $digest := (.Values.image.digest | default "") | toString | trim -}}
{{- if $digest -}}
{{- printf "%s@%s" .Values.image.repository $digest -}}
{{- else -}}
{{- printf "%s:%s" .Values.image.repository .Values.image.tag -}}
{{- end -}}
{{- end -}}

{{- /* Effective replica floor: max(replicaCount, HPA min, KEDA min when those are on). */ -}}
{{- define "daari.fleetReplicas" -}}
{{- $replicas := int .Values.replicaCount -}}
{{- if and .Values.autoscaling.enabled (gt (int .Values.autoscaling.minReplicas) $replicas) -}}
{{- $replicas = int .Values.autoscaling.minReplicas -}}
{{- end -}}
{{- $keda := .Values.autoscaling.keda | default dict -}}
{{- if and $keda.enabled (gt (int ($keda.minReplicaCount | default 1)) $replicas) -}}
{{- $replicas = int $keda.minReplicaCount -}}
{{- end -}}
{{- $replicas -}}
{{- end -}}

{{- define "daari.fleetSqliteWarning" -}}
{{- and (gt (int (include "daari.fleetReplicas" .)) 1) (not .Values.postgres.enabled) -}}
{{- end -}}

{{- /* Emit valueFrom.secretKeyRef env when secret.name is set. Args: name, secret */ -}}
{{- define "daari.webhookSecretEnv" -}}
{{- $env := index . 0 -}}
{{- $secret := index . 1 -}}
{{- if and $secret $secret.name }}
            - name: {{ $env }}
              valueFrom:
                secretKeyRef:
                  name: {{ $secret.name | quote }}
                  key: {{ $secret.key | default "webhook-secret" | quote }}
{{- end }}
{{- end -}}
