#!/bin/bash
set -e

echo "========================================="
echo "  FaceDeep - Azure VM Setup Script"
echo "========================================="

DOMAIN=${1:-facedeep.me}
APP_USER="facedeep"

echo "[1/8] System update..."
sudo apt-get update && sudo apt-get upgrade -y

echo "[2/8] Install Docker..."
curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
sudo sh /tmp/get-docker.sh
sudo usermod -aG docker $APP_USER

echo "[3/8] Install Docker Compose..."
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

echo "[4/8] Install Nginx..."
sudo apt-get install -y nginx certbot python3-certbot-nginx

echo "[5/8] Install monitoring tools..."
sudo apt-get install -y htop iotop net-tools

echo "[6/8] Create app directory..."
sudo mkdir -p /opt/facedeep
sudo chown -R $APP_USER:$APP_USER /opt/facedeep

echo "[7/8] Setup firewall..."
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

echo "[8/8] Done!"
echo ""
echo "========================================="
echo "  Next Steps:"
echo "========================================="
echo "1. Clone your repo:"
echo "   cd /opt/facedeep"
echo "   git clone https://github.com/yourusername/FaceDeep.git ."
echo ""
echo "2. Create .env file:"
echo "   cp .env.production .env"
echo "   nano .env"
echo ""
echo "3. Run setup SSL:"
echo "   sudo bash deploy/ssl-setup.sh $DOMAIN"
echo ""
echo "4. Start services:"
echo "   docker-compose -f deploy/docker-compose.prod.yml up -d --build"
echo "========================================="
