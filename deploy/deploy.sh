#!/bin/bash
set -e

DOMAIN=${1:?Usage: $0 <domain>}
APP_USER="facedeep"

echo "========================================="
echo "  FaceDeep - Full Deployment Script"
echo "========================================="
echo "Domain: $DOMAIN"
echo "========================================="

echo "[1/6] Updating system..."
sudo apt-get update && sudo apt-get upgrade -y

echo "[2/6] Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sudo sh /tmp/get-docker.sh
    sudo usermod -aG docker $APP_USER
fi

echo "[3/6] Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
      -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

echo "[4/6] Installing Nginx..."
sudo apt-get install -y nginx

echo "[5/6] Configuring firewall..."
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

echo "[6/6] Setting up app..."
sudo mkdir -p /opt/facedeep
sudo chown -R $APP_USER:$APP_USER /opt/facedeep

# Copy nginx config
sudo cp /opt/facedeep/deploy/nginx.conf /etc/nginx/sites-available/facedeep
sudo sed -i "s/DOMAIN_PLACEHOLDER/$DOMAIN/g" /etc/nginx/sites-available/facedeep
sudo ln -sf /etc/nginx/sites-available/facedeep /etc/nginx/sites-enabled/facedeep
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo ""
echo "========================================="
echo "  Setup Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Point your domain DNS to this server's IP"
echo "2. Run SSL setup:"
echo "   sudo bash deploy/ssl-setup.sh $DOMAIN your@email.com"
echo "3. Create .env file:"
echo "   cd /opt/facedeep"
echo "   cp .env.production .env"
echo "   nano .env"
echo "4. Start the app:"
echo "   docker-compose -f deploy/docker-compose.prod.yml up -d --build"
echo "========================================="
