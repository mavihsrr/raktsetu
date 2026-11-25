#!/usr/bin/env bash
# Creates the RaktSetu alert policies in Cloud Monitoring (project festivehackbuild).
# Usage: deploy/monitoring/alerts.sh [notification-channel-id]   (omit it: incidents show in the console only)
# Needs the app build that serves /metrics, plus deploy/k8s/monitoring.yaml applied.
set -euo pipefail
P=${GCP_PROJECT:-festivehackbuild}
CH=${1:+projects/$P/notificationChannels/$1}
tmp=$(mktemp -d)
mk() { # name, promql, duration, severity, documentation
  python3 - "$tmp/$1.json" "$1" "$2" "$3" "$4" "$5" "${CH:-}" <<'PY'
import json, sys
path, name, q, dur, sev, doc, ch = sys.argv[1:8]
p = {"displayName": f"RaktSetu: {name}", "combiner": "OR", "severity": sev,
     "conditions": [{"displayName": name, "conditionPrometheusQueryLanguage": {
         "query": q, "duration": dur, "evaluationInterval": "60s"}}],
     "documentation": {"content": doc, "mimeType": "text/markdown"}}
if ch: p["notificationChannels"] = [ch]
json.dump(p, open(path, "w"))
PY
  gcloud alpha monitoring policies create --project "$P" --policy-from-file "$tmp/$1.json" --quiet >/dev/null
  echo "created: RaktSetu: $1"
}
mk app-down 'absent(raktsetu_process_start_time_seconds{namespace="raktsetu"}) or (time() - max(raktsetu_process_start_time_seconds{namespace="raktsetu"}) < 0)' 180s CRITICAL "The app is not reporting metrics: pod down or crash-looping. NudgeBee should show the cause."
mk 5xx-errors 'sum(rate(raktsetu_http_requests_total{namespace="raktsetu",status=~"5.."}[5m])) > 0.05' 120s ERROR "The API is returning 5xx errors."
mk eraktkosh-failing 'sum(increase(raktsetu_eraktkosh_requests_total{namespace="raktsetu",outcome="error"}[10m])) >= 3' 0s ERROR "e-RaktKosh lookups keep failing, so searches can't find banks."
mk slow-search 'histogram_quantile(0.9, sum by (le) (rate(raktsetu_search_seconds_bucket{namespace="raktsetu"}[10m]))) > 12' 300s WARNING "p90 blood search is over 12 s (target: about 8 s)."
mk voice-sessions-failing 'sum(increase(raktsetu_voice_sessions_total{namespace="raktsetu",outcome="error"}[10m])) >= 3' 0s ERROR "Browser voice sessions keep failing to connect (Sarvam, agent version or API key)."
mk calls-failing 'sum(increase(raktsetu_calls_total{namespace="raktsetu",status="failed"}[15m])) >= 3' 0s WARNING "Confirmation calls keep failing."
echo "done. Notification channel: ${CH:-none (console only)}"
