{{/*
Expand the name of the chart.
*/}}
{{- define "argo-rollouts-skill.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Fully-qualified app name (release-name + chart-name).
*/}}
{{- define "argo-rollouts-skill.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "argo-rollouts-skill.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
app.kubernetes.io/name: {{ include "argo-rollouts-skill.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels — MUST be identical on Rollout.spec.selector and Pod template.
*/}}
{{- define "argo-rollouts-skill.selectorLabels" -}}
app.kubernetes.io/name: {{ include "argo-rollouts-skill.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
