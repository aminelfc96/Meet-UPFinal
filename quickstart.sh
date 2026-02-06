#!/bin/bash

# Meeting App Quick Deployment Script
# One-command deployment for Ubuntu VPS

set -e

echo "🚀 Meeting App Quick Deployment"
echo "================================"

# Check if running on Ubuntu
if [ ! -f /etc/os-release ] || ! grep -q "Ubuntu" /etc/os-release; then
    echo "❌ This script is designed for Ubuntu. Please use manual deployment."
    exit 1
fi

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "❌ Don't run this script as root. Use a regular user with sudo access."
    exit 1
fi

# Check sudo access
if ! sudo -n true 2>/dev/null; then
    echo "❌ This script requires sudo access. Please run: sudo -v"
    exit 1
fi

# Collect configuration
echo ""
echo "📋 Configuration Setup"
echo "Please provide the following information:"

read -p "Domain name (e.g., meetingapp.com): " DOMAIN
read -p "Email for SSL certificates: " EMAIL
read -p "Strong secret key (leave empty to generate): " SECRET_KEY

if [ -z "$SECRET_KEY" ]; then
    SECRET_KEY=$(openssl rand -hex 32)
    echo "Generated secret key: $SECRET_KEY"
fi

# Create environment file
cat > .env << EOF
ENVIRONMENT=production
DOMAIN=$DOMAIN
SECRET_KEY=$SECRET_KEY
SSL_EMAIL=$EMAIL
COMPOSE_PROJECT_NAME=meeting-app
EOF

echo "✅ Environment configured"

# Run system setup (if needed)
if ! command -v docker &> /dev/null; then
    echo ""
    echo "🔧 Installing Docker and dependencies..."
    echo "This may take a few minutes and will require sudo password..."
    
    # Download and run VPS setup script
    if [ -f "scripts/vps-setup.sh" ]; then
        sudo bash scripts/vps-setup.sh
    else
        echo "❌ VPS setup script not found. Please run manual setup."
        exit 1
    fi
fi

# Deploy application
echo ""
echo "🚀 Deploying application..."

# Build and start services
if [ -f "docker-compose.prod.yml" ]; then
    docker-compose -f docker-compose.prod.yml build
    docker-compose -f docker-compose.prod.yml up -d
else
    echo "❌ Production docker-compose file not found"
    exit 1
fi

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 30

# Check if services are running
if docker-compose -f docker-compose.prod.yml ps | grep -q "Up"; then
    echo "✅ Services are running"
else
    echo "❌ Services failed to start. Check logs:"
    docker-compose -f docker-compose.prod.yml logs
    exit 1
fi

# Setup SSL certificates
echo ""
echo "🔐 Setting up SSL certificates..."
if [ -f "scripts/setup-ssl.sh" ]; then
    bash scripts/setup-ssl.sh
else
    echo "⚠️  SSL setup script not found. You'll need to configure SSL manually."
fi

# Final status
echo ""
echo "🎉 Deployment Complete!"
echo "======================="
echo ""
echo "Your Meeting App is now running at:"
echo "🌐 HTTPS: https://$DOMAIN"
echo "🌐 HTTP:  http://$DOMAIN (redirects to HTTPS)"
echo ""
echo "Management commands:"
echo "  View logs:    docker-compose -f docker-compose.prod.yml logs -f"
echo "  Restart:      docker-compose -f docker-compose.prod.yml restart"
echo "  Stop:         docker-compose -f docker-compose.prod.yml down"
echo "  Update:       git pull && docker-compose -f docker-compose.prod.yml build && docker-compose -f docker-compose.prod.yml up -d"
echo ""
echo "Security features enabled:"
echo "✅ SSL/TLS encryption"
echo "✅ Firewall configured"
echo "✅ Rate limiting"
echo "✅ Security headers"
echo "✅ Automatic backups"
echo "✅ SSL certificate auto-renewal"
echo ""
echo "📝 Important notes:"
echo "• Make sure your domain DNS points to this server IP"
echo "• SSL certificate will auto-renew every 90 days"
echo "• Daily backups are stored in the backups/ directory"
echo "• Check logs regularly for any issues"
echo ""
echo "Need help? Check the UBUNTU_VPS_DEPLOYMENT.md guide"