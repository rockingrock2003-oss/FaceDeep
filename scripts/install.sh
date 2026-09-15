#!/bin/bash
# FaceDeep On-Premise Installation Script
# Usage: curl -sSL https://facedeep.com/install.sh | bash

set -e

FACEDEEP_VERSION="2.0.0"
INSTALL_DIR="/opt/facedeep"
DATA_DIR="/var/lib/facedeep"

echo "=== FaceDeep On-Premise Installer v${FACEDEEP_VERSION} ==="

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "Docker is required. Install it first."; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { echo "Docker Compose is required."; exit 1; }

# Create directories
sudo mkdir -p ${INSTALL_DIR} ${DATA_DIR}

# Download compose file
echo "Downloading configuration..."
sudo curl -sSL https://facedeep.com/docker-compose.production.yml \
    -o ${INSTALL_DIR}/docker-compose.yml

# Generate secrets
SECRET_KEY=$(openssl rand -hex 32)
DB_PASSWORD=$(openssl rand -hex 16)
JWT_SECRET=$(openssl rand -hex 32)

# Create .env file
cat > ${INSTALL_DIR}/.env <<EOF
FACEDEEP_VERSION=${FACEDEEP_VERSION}
SECRET_KEY=${SECRET_KEY}
POSTGRES_PASSWORD=${DB_PASSWORD}
JWT_SECRET=${JWT_SECRET}
REDIS_URL=redis://redis:6379/0
DATABASE_URL=postgresql+asyncpg://facedeep:${DB_PASSWORD}@postgres:5432/facedeep
ENVIRONMENT=production
SENTRY_DSN=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
EOF

echo "Starting FaceDeep..."
cd ${INSTALL_DIR}
sudo docker-compose up -d

echo ""
echo "=== FaceDeep Installed Successfully ==="
echo "Dashboard: http://localhost:3000"
echo "API: http://localhost:8000/docs"
echo "Config: ${INSTALL_DIR}/.env"
echo ""
echo "To update: sudo bash ${INSTALL_DIR}/update.sh"
echo "To uninstall: sudo bash ${INSTALL_DIR}/uninstall.sh"
