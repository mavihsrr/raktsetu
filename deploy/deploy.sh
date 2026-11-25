#!/usr/bin/env bash
# Build + deploy RaktSetu to GKE. Safe to re-run (rolls out a new image).
#   deploy/deploy.sh            build, push, apply
#   deploy/deploy.sh --no-build re-apply manifests/secrets with the last image
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT="${PROJECT:-festivehackbuild}"
REGION="${REGION:-asia-south1}"
CLUSTER="${CLUSTER:-raktsetu}"
REPO="$REGION-docker.pkg.dev/$PROJECT/raktsetu"
# Always the COMMITTED code (git HEAD): uncommitted edits never go live.
TAG="$(git rev-parse --short HEAD)"
IMAGE="$REPO/app:$TAG"

gcloud config set project "$PROJECT" >/dev/null
gcloud container clusters get-credentials "$CLUSTER" --region "$REGION" >/dev/null

if [[ "${1:-}" != "--no-build" ]]; then
  gcloud artifacts repositories describe raktsetu --location "$REGION" >/dev/null 2>&1 ||
    gcloud artifacts repositories create raktsetu --repository-format docker --location "$REGION" \
      --description "RaktSetu images"
  CTX="$(mktemp -d)"
  git archive HEAD | tar -x -C "$CTX"
  # Dockerfile/ignore files may be newer than HEAD; they hold no app code.
  cp Dockerfile .dockerignore .gcloudignore "$CTX"/
  echo "== building $IMAGE from commit $TAG (Cloud Build, linux/amd64)"
  gcloud builds submit --tag "$IMAGE" --region "$REGION" "$CTX"
  rm -rf "$CTX"
  echo "$IMAGE" > deploy/.last-image
fi
IMAGE="$(cat deploy/.last-image)"

kubectl apply -f - >/dev/null <<<"apiVersion: v1
kind: Namespace
metadata: {name: raktsetu}"

# App secrets from .env (server-only keys; laptop-only paths dropped). Values are never printed.
ENVF="$(mktemp)"; trap 'rm -f "$ENVF"' EXIT
python3 - <<'EOF' > "$ENVF"
import re
skip = {"DB_PATH", "LOCAL_FLAGS_PATH", "BACKEND_URL", "FLAGSMITH_ADMIN_KEY", "NUDGEBEE_AGENT_TOKEN"}
for line in open(".env"):
    m = re.match(r"\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$", line)
    if m and m.group(1) not in skip and m.group(2).strip():
        print(f"{m.group(1)}={m.group(2).strip().strip(chr(34)).strip(chr(39))}")
EOF
kubectl -n raktsetu create secret generic raktsetu-env --from-env-file="$ENVF" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
rm -f "$ENVF"

# ngrok authtoken from the laptop's ngrok config.
NGROK_CFG="$(ngrok config check 2>/dev/null | sed -n 's/^Valid configuration file at //p')"
NGROK_CFG="${NGROK_CFG:-$HOME/Library/Application Support/ngrok/ngrok.yml}"
TOKEN="$(sed -n 's/^ *authtoken: *//p' "$NGROK_CFG" | head -1 | tr -d '"')"
[[ -n "$TOKEN" ]] || { echo "no ngrok authtoken found in $NGROK_CFG"; exit 1; }
kubectl -n raktsetu create secret generic ngrok --from-literal=authtoken="$TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
unset TOKEN

DOMAIN="$(sed -En 's#^PUBLIC_BASE_URL=https?://##p' .env | tr -d '"/ ')"
sed -e "s#IMAGE_PLACEHOLDER#$IMAGE#" -e "s#NGROK_DOMAIN_PLACEHOLDER#$DOMAIN#" \
    -e "s#NGROK_REPLICAS_PLACEHOLDER#${NGROK_REPLICAS:-1}#" deploy/k8s/raktsetu.yaml |
  kubectl apply -f -
kubectl -n raktsetu rollout status deploy/raktsetu --timeout=300s
# The domain can be served by ONE ngrok agent only. NGROK_REPLICAS=0 keeps the laptop's tunnel in charge.
if [[ "${NGROK_REPLICAS:-1}" != "0" ]]; then
  kubectl -n raktsetu rollout status deploy/ngrok --timeout=180s
  echo "== live at https://$DOMAIN/healthz"
else
  echo "== app deployed; cluster ngrok held at 0 (laptop tunnel still serving $DOMAIN)"
fi
