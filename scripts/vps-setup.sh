#!/bin/bash

# Ubuntu VPS Automated Setup Script for Meeting App
# This script sets up Docker, SSL, and security configurations

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Meeting App VPS Setup Script${NC}"
echo "======================================"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ This script must be run as root (use sudo)${NC}"
    exit 1
fi

# Function to prompt for input
prompt_input() {
    local prompt="$1"
    local var_name="$2"
    local default="$3"
    
    if [ -n "$default" ]; then
        read -p "$prompt [$default]: " input
        eval "$var_name=\"\${input:-$default}\""
    else
        read -p "$prompt: " input
        eval "$var_name=\"$input\""
    fi
}

# Get server information
echo -e "\n${YELLOW}📋 Server Configuration${NC}"
SERVER_IP=$(curl -s ifconfig.me || curl -s ipinfo.io/ip || echo "unknown")
echo -e "Detected server IP: ${GREEN}$SERVER_IP${NC}"

prompt_input "Enter your domain name" DOMAIN
prompt_input "Enter email for SSL certificates" EMAIL
prompt_input "Enter SSH port" SSH_PORT "22"

# Update system
echo -e "\n${BLUE}🔄 Updating system packages...${NC}"
apt update && apt upgrade -y

# Install essential packages
echo -e "\n${BLUE}📦 Installing essential packages...${NC}"
apt install -y \
    curl \
    wget \
    git \
    ufw \
    fail2ban \
    htop \
    iotop \
    netstat-nat \
    unzip \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release

# Install Docker
echo -e "\n${BLUE}🐳 Installing Docker...${NC}"
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    systemctl enable docker
    systemctl start docker
    rm get-docker.sh
    echo -e "${GREEN}✅ Docker installed${NC}"
else
    echo -e "${GREEN}✅ Docker already installed${NC}"
fi

# Install Docker Compose
echo -e "\n${BLUE}🔧 Installing Docker Compose...${NC}"
if ! command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d\" -f4)
    curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    echo -e "${GREEN}✅ Docker Compose installed${NC}"
else
    echo -e "${GREEN}✅ Docker Compose already installed${NC}"
fi

# Configure firewall
echo -e "\n${BLUE}🔥 Configuring UFW firewall...${NC}"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow $SSH_PORT/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable
echo -e "${GREEN}✅ Firewall configured${NC}"

# Configure fail2ban
echo -e "\n${BLUE}🛡️ Configuring fail2ban...${NC}"
cat > /etc/fail2ban/jail.local << EOF
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3
backend = systemd

[sshd]
enabled = true
port = $SSH_PORT
filter = sshd
logpath = /var/log/auth.log
maxretry = 3

[nginx-http-auth]
enabled = true
filter = nginx-http-auth
port = http,https
logpath = /var/log/nginx/error.log

[nginx-limit-req]
enabled = true
filter = nginx-limit-req
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 10

[nginx-botsearch]
enabled = true
filter = nginx-botsearch
port = http,https
logpath = /var/log/nginx/access.log
maxretry = 2
EOF

systemctl enable fail2ban
systemctl restart fail2ban
echo -e "${GREEN}✅ Fail2ban configured${NC}"

# Create application directory
APP_DIR="/opt/meeting-app"
echo -e "\n${BLUE}📁 Creating application directory: $APP_DIR${NC}"
mkdir -p $APP_DIR
cd $APP_DIR

# Create necessary directories
mkdir -p {data,uploads,logs,ssl,scripts,backups}
chmod 755 {data,uploads,logs,backups}
chmod 700 ssl
chmod 755 scripts

# Create environment file template
echo -e "\n${BLUE}⚙️ Creating environment template...${NC}"
cat > .env.template << EOF
# Production Environment Configuration
ENVIRONMENT=production
DOMAIN=$DOMAIN
SERVER_IP=$SERVER_IP
SECRET_KEY=CHANGE_THIS_TO_A_RANDOM_64_CHARACTER_STRING

# SSL Configuration
SSL_EMAIL=$EMAIL
CERTBOT_EMAIL=$EMAIL

# Docker Configuration
COMPOSE_PROJECT_NAME=meeting-app
COMPOSE_FILE=docker-compose.prod.yml
EOF

# Create SSL setup script
cat > scripts/setup-ssl.sh << 'EOF'
#!/bin/bash

set -e

echo "🔐 Setting up SSL certificates with Let's Encrypt..."

# Load environment variables
if [ -f .env ]; then
    source .env
else
    echo "❌ .env file not found. Please create it first."
    exit 1
fi

# Validate required variables
if [ -z "$DOMAIN" ] || [ -z "$SSL_EMAIL" ]; then
    echo "❌ DOMAIN and SSL_EMAIL must be set in .env file"
    exit 1
fi

# Create webroot directory for ACME challenge
mkdir -p /var/www/certbot

# Create initial nginx config for ACME challenge
cat > nginx/nginx-acme.conf << 'NGINX_CONF'
events {
    worker_connections 1024;
}

http {
    server {
        listen 80;
        server_name _;
        
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }
        
        location / {
            return 200 'ACME Challenge Server';
            add_header Content-Type text/plain;
        }
    }
}
NGINX_CONF

# Start nginx for ACME challenge
echo "Starting nginx for ACME challenge..."
docker run -d --name nginx-acme \
    -p 80:80 \
    -v $(pwd)/nginx/nginx-acme.conf:/etc/nginx/nginx.conf:ro \
    -v /var/www/certbot:/var/www/certbot:ro \
    nginx:alpine

# Wait for nginx to start
sleep 5

# Request SSL certificate
echo "Requesting SSL certificate for $DOMAIN..."
docker run --rm \
    -v $(pwd)/ssl:/etc/letsencrypt \
    -v /var/www/certbot:/var/www/certbot \
    certbot/certbot \
    certonly --webroot \
    --webroot-path=/var/www/certbot \
    --email $SSL_EMAIL \
    --agree-tos \
    --no-eff-email \
    -d $DOMAIN

# Stop ACME nginx
docker stop nginx-acme
docker rm nginx-acme

# Check if certificate was obtained
if [ -f "ssl/live/$DOMAIN/fullchain.pem" ]; then
    echo "✅ SSL certificate obtained successfully!"
    
    # Copy certificates to nginx directory
    mkdir -p ssl/nginx
    cp ssl/live/$DOMAIN/fullchain.pem ssl/nginx/
    cp ssl/live/$DOMAIN/privkey.pem ssl/nginx/
    
    echo "✅ SSL setup complete!"
else
    echo "❌ Failed to obtain SSL certificate"
    exit 1
fi
EOF

chmod +x scripts/setup-ssl.sh

# Create backup script
cat > scripts/backup.sh << 'EOF'
#!/bin/bash

set -e

echo "💾 Creating backup..."

# Create backup directory
BACKUP_DIR="backups"
mkdir -p $BACKUP_DIR

# Generate timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_$TIMESTAMP.tar.gz"

# Create backup
tar -czf $BACKUP_FILE data/ uploads/ .env logs/

# Keep only last 7 backups
find $BACKUP_DIR -name "backup_*.tar.gz" -type f -mtime +7 -delete

echo "✅ Backup created: $BACKUP_FILE"

# Optional: Upload to remote storage (uncomment and configure)
# aws s3 cp $BACKUP_FILE s3://your-backup-bucket/
# scp $BACKUP_FILE user@backup-server:/path/to/backups/
EOF

chmod +x scripts/backup.sh

# Create management script
cat > scripts/manage.sh << 'EOF'
#!/bin/bash

# Meeting App Management Script

APP_DIR="/opt/meeting-app"
cd $APP_DIR

case "$1" in
    start)
        echo "🚀 Starting Meeting App..."
        docker-compose -f docker-compose.prod.yml up -d
        ;;
    stop)
        echo "🛑 Stopping Meeting App..."
        docker-compose -f docker-compose.prod.yml down
        ;;
    restart)
        echo "🔄 Restarting Meeting App..."
        docker-compose -f docker-compose.prod.yml restart
        ;;
    logs)
        echo "📋 Showing logs..."
        docker-compose -f docker-compose.prod.yml logs -f "${2:-}"
        ;;
    status)
        echo "📊 Service Status:"
        docker-compose -f docker-compose.prod.yml ps
        ;;
    update)
        echo "🔄 Updating application..."
        git pull
        docker-compose -f docker-compose.prod.yml build --no-cache
        docker-compose -f docker-compose.prod.yml up -d
        ;;
    backup)
        echo "💾 Creating backup..."
        ./scripts/backup.sh
        ;;
    renew-ssl)
        echo "🔐 Renewing SSL certificate..."
        docker run --rm \
            -v $(pwd)/ssl:/etc/letsencrypt \
            -v /var/www/certbot:/var/www/certbot \
            certbot/certbot renew
        docker-compose -f docker-compose.prod.yml restart nginx
        ;;
    health)
        echo "🏥 Health check..."
        curl -f http://localhost/health || echo "❌ Health check failed"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|logs|status|update|backup|renew-ssl|health}"
        echo ""
        echo "Examples:"
        echo "  $0 logs webapp    # Show webapp logs"
        echo "  $0 logs nginx     # Show nginx logs"
        exit 1
        ;;
esac
EOF

chmod +x scripts/manage.sh

# Create systemd service
echo -e "\n${BLUE}⚙️ Creating systemd service...${NC}"
cat > /etc/systemd/system/meeting-app.service << EOF
[Unit]
Description=Meeting App
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$APP_DIR
ExecStart=/usr/local/bin/docker-compose -f docker-compose.prod.yml up -d
ExecStop=/usr/local/bin/docker-compose -f docker-compose.prod.yml down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable meeting-app

# Set up cron jobs
echo -e "\n${BLUE}⏰ Setting up cron jobs...${NC}"

# SSL renewal (weekly)
(crontab -l 2>/dev/null; echo "0 3 * * 0 cd $APP_DIR && ./scripts/manage.sh renew-ssl") | crontab -

# Backup (daily)
(crontab -l 2>/dev/null; echo "0 2 * * * cd $APP_DIR && ./scripts/backup.sh") | crontab -

# System maintenance (weekly)
cat > scripts/maintenance.sh << 'EOF'
#!/bin/bash

echo "🧹 Performing system maintenance..."

# Update system packages
apt update && apt upgrade -y

# Clean up Docker
docker system prune -f

# Clean up old logs
find /var/log -name "*.log" -type f -mtime +30 -exec gzip {} \;
find /var/log -name "*.log.gz" -type f -mtime +90 -delete

# Restart services
systemctl restart fail2ban
systemctl restart docker

echo "✅ Maintenance complete!"
EOF

chmod +x scripts/maintenance.sh
(crontab -l 2>/dev/null; echo "0 4 * * 0 cd $APP_DIR && ./scripts/maintenance.sh") | crontab -

# Create monitoring script
cat > scripts/monitor.sh << 'EOF'
#!/bin/bash

echo "📊 System Status Report"
echo "======================"

# System information
echo "🖥️  System:"
echo "   Uptime: $(uptime -p)"
echo "   Load: $(uptime | awk -F'load average:' '{print $2}')"
echo "   Memory: $(free -h | awk 'NR==2{printf "%.1f%% used (%s/%s)", $3*100/$2, $3, $2}')"
echo "   Disk: $(df -h / | awk 'NR==2{printf "%s used (%s available)", $5, $4}')"

echo ""
echo "🐳 Docker Status:"
docker-compose -f docker-compose.prod.yml ps

echo ""
echo "🔥 Firewall Status:"
ufw status numbered | head -10

echo ""
echo "🛡️  Fail2ban Status:"
fail2ban-client status | head -5

echo ""
echo "📈 Resource Usage:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"
EOF

chmod +x scripts/monitor.sh

# Set proper ownership
chown -R root:root $APP_DIR
chown -R www-data:www-data $APP_DIR/{uploads,logs}

echo -e "\n${GREEN}✅ VPS setup completed successfully!${NC}"
echo -e "\n${YELLOW}📋 Next Steps:${NC}"
echo "1. Upload your application code to: $APP_DIR"
echo "2. Copy .env.template to .env and configure:"
echo "   cp .env.template .env"
echo "   nano .env"
echo "3. Set up SSL certificates:"
echo "   ./scripts/setup-ssl.sh"
echo "4. Start the application:"
echo "   ./scripts/manage.sh start"
echo ""
echo -e "${BLUE}🔧 Management Commands:${NC}"
echo "  ./scripts/manage.sh start     - Start the application"
echo "  ./scripts/manage.sh stop      - Stop the application"
echo "  ./scripts/manage.sh restart   - Restart the application"
echo "  ./scripts/manage.sh logs      - View logs"
echo "  ./scripts/manage.sh status    - Check status"
echo "  ./scripts/manage.sh health    - Health check"
echo "  ./scripts/manage.sh backup    - Create backup"
echo "  ./scripts/manage.sh renew-ssl - Renew SSL certificate"
echo "  ./scripts/monitor.sh          - System status report"
echo ""
echo -e "${GREEN}🌐 Your app will be available at: https://$DOMAIN${NC}"
echo -e "${GREEN}🔧 Application directory: $APP_DIR${NC}"
echo -e "${GREEN}🔒 SSL certificates will auto-renew weekly${NC}"
echo -e "${GREEN}💾 Backups will be created daily${NC}"