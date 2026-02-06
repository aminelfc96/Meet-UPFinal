#!/bin/bash

# Meeting App Production Deployment Script
# Enhanced version with SSL support and production features

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        print_error "This script should not be run as root for security reasons"
        exit 1
    fi
}

# Check if Docker is installed
check_docker() {
    print_status "Checking Docker installation..."
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        echo "Visit: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        echo "Visit: https://docs.docker.com/compose/install/"
        exit 1
    fi
    
    print_success "Docker and Docker Compose are installed"
}

# Check if user is in docker group
check_docker_permissions() {
    print_status "Checking Docker permissions..."
    if ! docker ps &> /dev/null; then
        print_error "Cannot run Docker commands. Add your user to the docker group:"
        echo "sudo usermod -aG docker \$USER"
        echo "Then log out and log back in."
        exit 1
    fi
    print_success "Docker permissions are configured"
}

# Create SSL directory
setup_ssl_directory() {
    print_status "Setting up SSL directory..."
    mkdir -p ssl
    
    if [[ ! -f ssl/cert.pem || ! -f ssl/key.pem ]]; then
        print_warning "SSL certificates not found in ssl/ directory"
        echo ""
        echo "You need to place your SSL certificates in the ssl/ directory:"
        echo "  ssl/cert.pem  - Your SSL certificate"
        echo "  ssl/key.pem   - Your SSL private key"
        echo ""
        echo "For testing purposes, you can generate self-signed certificates:"
        echo "  openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem -out ssl/cert.pem -days 365 -nodes"
        echo ""
        read -p "Do you want to generate self-signed certificates for testing? [y/N]: " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            generate_self_signed_certs
        else
            print_error "SSL certificates are required. Please add them to ssl/ directory and run again."
            exit 1
        fi
    else
        print_success "SSL certificates found"
    fi
}

# Generate self-signed certificates
generate_self_signed_certs() {
    print_status "Generating self-signed SSL certificates..."
    
    read -p "Enter your domain name (or localhost for local testing): " domain
    domain=${domain:-localhost}
    
    openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem -out ssl/cert.pem -days 365 -nodes \
        -subj "/C=US/ST=State/L=City/O=Organization/CN=${domain}"
    
    print_success "Self-signed certificates generated for ${domain}"
    print_warning "Remember: Self-signed certificates will show security warnings in browsers"
}

# Create necessary directories
setup_directories() {
    print_status "Creating necessary directories..."
    mkdir -p data uploads logs ssl
    print_success "Directories created"
}

# Stop existing containers
stop_existing() {
    print_status "Stopping existing containers..."
    docker-compose down --remove-orphans 2>/dev/null || true
    print_success "Existing containers stopped"
}

# Build and start services
deploy_services() {
    print_status "Building and starting services..."
    
    # Check if production environment
    if [ -f "docker-compose.prod.yml" ] && [ "${ENVIRONMENT:-}" = "production" ]; then
        print_status "Using production configuration..."
        COMPOSE_FILE="docker-compose.prod.yml"
    else
        print_status "Using development configuration..."
        COMPOSE_FILE="docker-compose.yml"
    fi
    
    # Build the application
    docker-compose -f $COMPOSE_FILE build --no-cache
    
    # Start services
    docker-compose -f $COMPOSE_FILE up -d
    
    print_success "Services deployed using $COMPOSE_FILE"
}

# Wait for services to be ready
wait_for_services() {
    print_status "Waiting for services to be ready..."
    
    # Wait for webapp to be healthy
    local max_attempts=30
    local attempt=0
    
    while [[ $attempt -lt $max_attempts ]]; do
        if docker-compose ps webapp | grep -q "Up (healthy)"; then
            break
        fi
        
        if docker-compose ps webapp | grep -q "Exit"; then
            print_error "WebApp container failed to start"
            docker-compose logs webapp
            exit 1
        fi
        
        sleep 2
        ((attempt++))
        echo -n "."
    done
    
    echo ""
    
    if [[ $attempt -eq $max_attempts ]]; then
        print_error "Services did not become ready in time"
        docker-compose logs
        exit 1
    fi
    
    print_success "Services are ready"
}

# Show deployment status
show_status() {
    print_status "Deployment Status:"
    echo ""
    docker-compose ps
    echo ""
    
    # Get the IP address
    local ip=$(curl -s ifconfig.me || echo "localhost")
    
    print_success "Deployment completed successfully!"
    echo ""
    echo "Access your application at:"
    echo "  HTTPS: https://${ip}"
    echo "  HTTP:  http://${ip} (redirects to HTTPS)"
    echo ""
    echo "Management commands:"
    echo "  View logs:    docker-compose logs -f"
    echo "  Stop:         docker-compose down"
    echo "  Restart:      docker-compose restart"
    echo "  Update:       ./deploy.sh"
    echo ""
}

# Main deployment function
main() {
    echo "================================================"
    echo "      WebApp Production Deployment Script      "
    echo "================================================"
    echo ""
    
    check_root
    check_docker
    check_docker_permissions
    setup_directories
    setup_ssl_directory
    stop_existing
    deploy_services
    wait_for_services
    show_status
}

# Handle script arguments
case "${1:-deploy}" in
    "deploy")
        main
        ;;
    "stop")
        print_status "Stopping all services..."
        docker-compose down
        print_success "All services stopped"
        ;;
    "restart")
        print_status "Restarting services..."
        docker-compose restart
        print_success "Services restarted"
        ;;
    "logs")
        docker-compose logs -f
        ;;
    "status")
        docker-compose ps
        ;;
    "update")
        print_status "Updating deployment..."
        docker-compose down
        docker-compose build --no-cache
        docker-compose up -d
        print_success "Deployment updated"
        ;;
    "backup")
        print_status "Creating backup..."
        timestamp=$(date +%Y%m%d_%H%M%S)
        docker run --rm -v webapp_webapp_data:/data -v $(pwd):/backup alpine \
            tar czf /backup/webapp_backup_${timestamp}.tar.gz -C /data .
        print_success "Backup created: webapp_backup_${timestamp}.tar.gz"
        ;;
    "help"|"-h"|"--help")
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  deploy   - Deploy the application (default)"
        echo "  stop     - Stop all services"
        echo "  restart  - Restart all services"
        echo "  logs     - Show and follow logs"
        echo "  status   - Show service status"
        echo "  update   - Update and redeploy"
        echo "  backup   - Create data backup"
        echo "  help     - Show this help"
        ;;
    *)
        print_error "Unknown command: $1"
        echo "Use '$0 help' for available commands"
        exit 1
        ;;
esac