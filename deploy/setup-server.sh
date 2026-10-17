#!/usr/bin/env bash
# One-shot setup of a fresh Ubuntu 24.04 server (e.g. AWS EC2) for FaceGate.
#
#   bash deploy/setup-server.sh <domain>
#
# Installs Docker, creates .env with freshly generated secrets (only the first
# time), builds the image and starts FaceGate behind Caddy (HTTPS). Safe to
# run again after updating the code: secrets are kept, containers rebuilt.
set -euo pipefail

DOMAIN="${1:?usage: bash deploy/setup-server.sh <domain>   e.g. 3-91-12-34.sslip.io}"
cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1; then
  echo "== Installing Docker"
  sudo apt-get update -y
  sudo apt-get install -y docker.io docker-compose-v2
  sudo systemctl enable --now docker
fi

# Small instances (1-2 GB) need swap headroom while building the image.
if [ "$(swapon --show | wc -l)" -eq 0 ] && [ ! -f /swapfile ]; then
  echo "== Adding 2 GB swap"
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab >/dev/null
fi

if [ ! -f .env ]; then
  echo "== Generating secrets in .env"
  umask 077
  cat > .env <<EOF
DOMAIN=${DOMAIN}
FACEGATE_PUBLIC_BASE_URL=https://${DOMAIN}
FACEGATE_API_KEYS=lk_$(openssl rand -hex 24)
FACEGATE_DATA_KEY=$(openssl rand -base64 32)
FACEGATE_ADMIN_TOKEN=$(openssl rand -hex 24)
FACEGATE_CREDENTIALS=AKIA$(openssl rand -hex 8 | tr 'a-f' 'A-F'):$(openssl rand -hex 24)
EOF
else
  # Keep existing secrets; only update the domain.
  sed -i "s#^DOMAIN=.*#DOMAIN=${DOMAIN}#; s#^FACEGATE_PUBLIC_BASE_URL=.*#FACEGATE_PUBLIC_BASE_URL=https://${DOMAIN}#" .env
fi

# NO_BUILD=1 reuses an image loaded with `docker load` (copied from another
# server) instead of building: building drains a burstable server's CPU credits.
if [ "${NO_BUILD:-0}" = "1" ]; then
  echo "== Starting with the existing facegate image (no build)"
  sudo docker compose --env-file .env -f deploy/docker-compose.aws.yml up -d --no-build
else
  echo "== Building and starting (first build takes a few minutes)"
  sudo docker compose --env-file .env -f deploy/docker-compose.aws.yml up -d --build
fi

echo "== Waiting for https://${DOMAIN}/health"
for _ in $(seq 1 60); do
  if curl -fsS "https://${DOMAIN}/health" >/dev/null 2>&1; then
    echo "FaceGate is live at https://${DOMAIN}"
    echo "API key (x-api-key): $(grep '^FACEGATE_API_KEYS=' .env | cut -d= -f2 | cut -d, -f1)"
    exit 0
  fi
  sleep 5
done
echo "Not reachable yet. Check: sudo docker compose -f deploy/docker-compose.aws.yml logs" >&2
exit 1
