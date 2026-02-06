# Ubuntu VPS Deployment Guide

Complete guide for deploying the Meeting App on Ubuntu VPS with HTTPS support via Let's Encrypt.

## Prerequisites

- Ubuntu 20.04+ VPS with root access
- Domain name pointing to your VPS IP
- At least 2GB RAM and 20GB storage

## Quick Deployment

### 1. Run the Automated Setup Script

```bash
# Download and run the deployment script
wget https://raw.githubusercontent.com/your-repo/webapp/main/scripts/vps-setup.sh
chmod +x vps-setup.sh
sudo ./vps-setup.sh
```

### 2. Deploy Your Application

```bash
# Clone your repository
git clone https://github.com/your-repo/webapp.git
cd webapp

# Run the deployment
./deploy.sh
```

## Manual Step-by-Step Setup

### 1. System Update and Basic Security

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install essential packages
sudo apt install -y curl wget git ufw fail2ban htop

# Configure firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# Configure fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 2. Install Docker and Docker Compose

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Enable Docker service
sudo systemctl enable docker
sudo systemctl start docker

# Log out and back in for group changes to take effect
```

### 3. Clone and Prepare Application

```bash
# Clone the repository
git clone https://github.com/your-repo/webapp.git
cd webapp

# Create environment file
cp .env.example .env

# Edit environment variables
nano .env
```

Set these variables in `.env`:
```bash
ENVIRONMENT=production
DOMAIN=yourdomain.com
SECRET_KEY=your-super-secret-key-64-characters-minimum
SSL_EMAIL=your-email@domain.com
```

### 4. SSL Certificate Setup

The deployment includes automatic SSL certificate setup with Let's Encrypt:

```bash
# Create SSL certificate
./scripts/setup-ssl.sh
```

### 5. Deploy Application

```bash
# Deploy with Docker Compose
docker-compose -f docker-compose.prod.yml up -d

# Check status
docker-compose -f docker-compose.prod.yml ps
```

## Environment Configuration

### Production Environment Variables

Create `.env` file with:

```bash
# Environment
ENVIRONMENT=production

# Domain Configuration
DOMAIN=yourdomain.com
SERVER_IP=your.vps.ip.address

# Security
SECRET_KEY=generate-a-64-character-random-string-here

# SSL Configuration
SSL_EMAIL=admin@yourdomain.com
CERTBOT_EMAIL=admin@yourdomain.com

# Database (optional overrides)
DATABASE_PATH=/app/data/meeting_app.db

# CORS Origins (automatically configured based on DOMAIN)
# ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

### CORS Configuration

The application automatically configures CORS based on your domain:

- `https://yourdomain.com`
- `https://www.yourdomain.com`
- `https://your-server-ip` (if SERVER_IP is set)

## SSL Certificate Management

### Automatic Certificate Renewal

SSL certificates automatically renew via cron job. Manual renewal:

```bash
# Renew certificate
docker-compose -f docker-compose.prod.yml run --rm certbot renew

# Restart nginx to load new certificate
docker-compose -f docker-compose.prod.yml restart nginx
```

### Custom SSL Certificates

If you have custom SSL certificates:

```bash
# Create SSL directory
mkdir -p ssl

# Copy your certificates
cp your-certificate.pem ssl/fullchain.pem
cp your-private-key.pem ssl/privkey.pem

# Update docker-compose.prod.yml to mount custom certs
```

## Management Commands

### Application Management

```bash
# Start application
docker-compose -f docker-compose.prod.yml up -d

# Stop application
docker-compose -f docker-compose.prod.yml down

# Restart application
docker-compose -f docker-compose.prod.yml restart

# View logs
docker-compose -f docker-compose.prod.yml logs -f

# Check status
docker-compose -f docker-compose.prod.yml ps
```

### System Management

```bash
# System status
systemctl status meeting-app
htop

# Check disk usage
df -h
du -sh /opt/meeting-app/*

# Check network connections
netstat -tulpn | grep :80
netstat -tulpn | grep :443
```

### Backup and Restore

```bash
# Create backup
tar -czf backup-$(date +%Y%m%d-%H%M%S).tar.gz data/ uploads/

# Automated backup script
./scripts/backup.sh

# Restore from backup
tar -xzf backup-YYYYMMDD-HHMMSS.tar.gz
```

## Monitoring and Maintenance

### Log Management

```bash
# Application logs
docker-compose -f docker-compose.prod.yml logs webapp

# Nginx logs
docker-compose -f docker-compose.prod.yml logs nginx

# System logs
journalctl -u meeting-app -f

# Log rotation (automatic via logrotate)
sudo logrotate -f /etc/logrotate.d/docker-containers
```

### Performance Monitoring

```bash
# Resource usage
docker stats

# System resources
htop
iostat
free -h

# Network monitoring
iftop
```

### Security Monitoring

```bash
# Check fail2ban status
sudo fail2ban-client status

# Check firewall status
sudo ufw status verbose

# Check for intrusion attempts
sudo grep "Failed password" /var/log/auth.log | tail -10
```

## Troubleshooting

### Common Issues

#### 1. SSL Certificate Issues
```bash
# Check certificate status
echo | openssl s_client -connect yourdomain.com:443 -servername yourdomain.com

# Force certificate renewal
docker-compose -f docker-compose.prod.yml run --rm certbot renew --force-renewal
```

#### 2. Application Not Starting
```bash
# Check container logs
docker-compose -f docker-compose.prod.yml logs webapp

# Check container status
docker-compose -f docker-compose.prod.yml ps

# Restart services
docker-compose -f docker-compose.prod.yml restart
```

#### 3. Database Issues
```bash
# Check database file permissions
ls -la data/

# Database backup
cp data/meeting_app.db data/meeting_app.db.backup

# Reset database (WARNING: This will delete all data)
rm data/meeting_app.db
docker-compose -f docker-compose.prod.yml restart webapp
```

#### 4. Network Issues
```bash
# Check port availability
netstat -tulpn | grep :80
netstat -tulpn | grep :443

# Test internal connectivity
docker-compose -f docker-compose.prod.yml exec nginx wget -O- http://webapp:8000/health

# Check DNS resolution
nslookup yourdomain.com
```

### Health Checks

```bash
# Application health
curl -k https://yourdomain.com/health

# Database connectivity
docker-compose -f docker-compose.prod.yml exec webapp python -c "import sqlite3; conn = sqlite3.connect('/app/data/meeting_app.db'); print('Database OK')"

# WebSocket connectivity
wscat -c wss://yourdomain.com/ws/test
```

## Performance Optimization

### Nginx Optimization

The included nginx configuration includes:
- Gzip compression
- Static file caching
- Rate limiting
- Security headers
- HTTP/2 support

### Application Optimization

- Database connection pooling
- File upload optimization
- WebSocket connection limits
- Memory usage monitoring

### System Optimization

```bash
# Increase file descriptor limits
echo "fs.file-max = 100000" >> /etc/sysctl.conf

# Optimize network settings
echo "net.core.somaxconn = 1024" >> /etc/sysctl.conf
echo "net.ipv4.tcp_max_syn_backlog = 1024" >> /etc/sysctl.conf

# Apply changes
sysctl -p
```

## Scaling and High Availability

### Horizontal Scaling

For multiple servers:

```bash
# Load balancer configuration
# Set up nginx as load balancer on separate server
# Configure database replication
# Implement session store (Redis/PostgreSQL)
```

### Vertical Scaling

```bash
# Increase server resources
# Update Docker memory limits in docker-compose.prod.yml
# Optimize database configuration
```

## Backup Strategy

### Automated Backups

```bash
# Daily backup cron job
0 2 * * * cd /opt/meeting-app && ./scripts/backup.sh

# Weekly full system backup
0 3 * * 0 tar -czf /backups/full-backup-$(date +\%Y\%m\%d).tar.gz /opt/meeting-app
```

### Backup Storage

- Local backups: `/opt/meeting-app/backups/`
- Remote backups: Configure S3, FTP, or rsync
- Database dumps: Include SQL exports

## Security Best Practices

### Server Security

1. Regular security updates
2. SSH key authentication only
3. Fail2ban configuration
4. Firewall rules
5. SSL/TLS encryption
6. Security headers

### Application Security

1. Strong secret keys
2. CSRF protection (when enabled)
3. Rate limiting
4. Input validation
5. File upload restrictions
6. WebSocket authentication

### Monitoring Security

1. Log analysis
2. Intrusion detection
3. Vulnerability scanning
4. Security audit logs

## Support and Maintenance

### Regular Maintenance Tasks

Weekly:
- Check application logs
- Review system resources
- Update security patches
- Backup verification

Monthly:
- SSL certificate check
- Performance review
- Security audit
- Dependency updates

### Getting Help

1. Check application logs first
2. Review this deployment guide
3. Check GitHub issues
4. Contact support team

## Production Checklist

Before going live:

- [ ] Domain DNS configured
- [ ] SSL certificate installed and tested
- [ ] Environment variables set
- [ ] Database initialized
- [ ] Backups configured
- [ ] Monitoring set up
- [ ] Security hardening complete
- [ ] Performance testing done
- [ ] Health checks passing
- [ ] Documentation reviewed