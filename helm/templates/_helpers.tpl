{{- define "intune-device-healer.fullname" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}-healer
{{- end }}
