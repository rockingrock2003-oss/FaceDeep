#!/bin/bash
set -e

DOMAIN=${1:?Usage: $0 <domain>}
EMAIL=${2:?Usage: $0 <domain> <email>}

echo "========================================="
echo "  FaceDeep - SSL Certificate Setup"
echo "========================================="
echo "Domain: $DOMAIN"
echo "Email:  $EMAIL"
echo "========================================="

echo "[1/4] Installing Certbot..."
sudo apt-get install -y certbot python3-certbot-nginx

echo "[2/4] Obtaining SSL certificate..."
sudo certbot certonly \
  --standalone \
  --non-interactive \
  --agree-tos \
  --email "$EMAIL" \
  -d "$DOMAIN"

echo "[3/4] Setting up auto-renewal..."
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer

echo "[4/4] Testing renewal..."
sudo certbot renew --dry-run

echo ""
echo "========================================="
echo "  SSL Certificate Installed!"
echo "========================================="
echo "Certificate: /etc/letsencrypt/live/$DOMAIN/fullchain.pem"
echo "Key:         /etc/letsencrypt/live/$DOMAIN/privkey.pem"
echo ""
echo "Auto-renewal is configured."
echo "========================================="
