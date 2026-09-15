{{- define "daari.fullname" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- /* Effective replica floor: max(replicaCount, HPA min when autoscaling on). */ -}}
{{- define "daari.fleetReplicas" -}}
{{- $replicas := int .Values.replicaCount -}}
{{- if and .Values.autoscaling.enabled (gt (int .Values.autoscaling.minReplicas) $replicas) -}}
{{- $replicas = int .Values.autoscaling.minReplicas -}}
{{- end -}}
{{- $replicas -}}
{{- end -}}

{{- define "daari.fleetSqliteWarning" -}}
{{- and (gt (int (include "daari.fleetReplicas" .)) 1) (not .Values.postgres.enabled) -}}
{{- end -}}
