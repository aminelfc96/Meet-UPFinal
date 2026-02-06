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
        print_warning "Running as root is not recommended but allowed."
        print_warning "Ensure you know what you are doing."
        # No exit, just warning for VPS users who are often root
    fi
}

# Check if Docker is installed and determine compose command
check_docker() {
    print_status "Checking Docker installation..."
    
    # Check for docker engine
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        echo "Visit: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    # Determine Docker Compose command
    if command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker-compose"
        print_success "Found docker-compose (standalone)"
    elif docker compose version &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker compose"
        print_success "Found docker compose (plugin)"
    else
        print_error "Docker Compose is not installed (neither standalone nor plugin found)."
        echo "Visit: https://docs.docker.com/compose/install/"
        exit 1
    fi
    
    print_success "Docker configuration verified"
}

# Check if user is in docker group
check_docker_permissions() {
    print_status "Checking Docker permissions..."
    # Skip permission check if root
    if [[ $EUID -eq 0 ]]; then
        return
    fi
    
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
    $DOCKER_COMPOSE_CMD down --remove-orphans 2>/dev/null || true
    print_success "Existing containers stopped"
}

# Build and start services
deploy_services() {
    print_status "Building and starting services..."
    
    # Check if production environment or if prod file simply exists (default to prod for VPS)
    if [ -f "docker-compose.prod.yml" ]; then
        print_status "Using production configuration..."
        COMPOSE_FILE="docker-compose.prod.yml"
    else
        print_status "Using development configuration..."
        COMPOSE_FILE="docker-compose.yml"
    fi
    
    # Build the application
    $DOCKER_COMPOSE_CMD -f $COMPOSE_FILE build --no-cache
    
    # Start services
    $DOCKER_COMPOSE_CMD -f $COMPOSE_FILE up -d
    
    print_success "Services deployed using $COMPOSE_FILE"
}

# Wait for services to be ready
wait_for_services() {
    print_status "Waiting for services to be ready..."
    
    # Wait for webapp to be healthy
    local max_attempts=30
    local attempt=0
    
    while [[ $attempt -lt $max_attempts ]]; do
        if $DOCKER_COMPOSE_CMD ps webapp | grep -q "Up (healthy)"; then
            break
        fi
        
        if $DOCKER_COMPOSE_CMD ps webapp | grep -q "Exit"; then
            print_error "WebApp container failed to start"
            $DOCKER_COMPOSE_CMD logs webapp
            exit 1
        fi
        
        sleep 2
        ((attempt++))
        echo -n "."
    done
    
    echo ""
    
    if [[ $attempt -eq $max_attempts ]]; then
        print_error "Services did not become ready in time"
        $DOCKER_COMPOSE_CMD logs
        exit 1
    fi
    
    print_success "Services are ready"
}

# Show deployment status
show_status() {
    print_status "Deployment Status:"
    echo ""
    $DOCKER_COMPOSE_CMD ps
    echo ""
    
    # Get the IP address (Force IPv4)
    local ip=$(curl -4 -s ifconfig.me || echo "localhost")
    
    print_success "Deployment completed successfully!"
    echo ""
    echo "Access your application at:"
    echo "  HTTPS: https://${ip}"
    echo "  HTTP:  http://${ip} (redirects to HTTPS)"
    echo ""
    echo "Management commands:"
    echo "  View logs:    ./deploy.sh logs"
    echo "  Stop:         ./deploy.sh stop"
    echo "  Restart:      ./deploy.sh restart"
    echo "  Update:       ./deploy.sh update"
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
        # Ensure we have the command before trying to stop if run standalone
        if [ -z "$DOCKER_COMPOSE_CMD" ]; then
             if command -v docker-compose &> /dev/null; then DOCKER_COMPOSE_CMD="docker-compose"; else DOCKER_COMPOSE_CMD="docker compose"; fi
        fi
        print_status "Stopping all services..."
        $DOCKER_COMPOSE_CMD down
        print_success "All services stopped"
        ;;
    "restart")
        if [ -z "$DOCKER_COMPOSE_CMD" ]; then
             if command -v docker-compose &> /dev/null; then DOCKER_COMPOSE_CMD="docker-compose"; else DOCKER_COMPOSE_CMD="docker compose"; fi
        fi
        print_status "Restarting services..."
        $DOCKER_COMPOSE_CMD restart
        print_success "Services restarted"
        ;;
    "logs")
        if [ -z "$DOCKER_COMPOSE_CMD" ]; then
             if command -v docker-compose &> /dev/null; then DOCKER_COMPOSE_CMD="docker-compose"; else DOCKER_COMPOSE_CMD="docker compose"; fi
        fi
        $DOCKER_COMPOSE_CMD logs -f
        ;;
    "status")
        if [ -z "$DOCKER_COMPOSE_CMD" ]; then
             if command -v docker-compose &> /dev/null; then DOCKER_COMPOSE_CMD="docker-compose"; else DOCKER_COMPOSE_CMD="docker compose"; fi
        fi
        $DOCKER_COMPOSE_CMD ps
        ;;
    "update")
        if [ -z "$DOCKER_COMPOSE_CMD" ]; then
             if command -v docker-compose &> /dev/null; then DOCKER_COMPOSE_CMD="docker-compose"; else DOCKER_COMPOSE_CMD="docker compose"; fi
        fi
        print_status "Updating deployment..."
        $DOCKER_COMPOSE_CMD down
        $DOCKER_COMPOSE_CMD build --no-cache
        $DOCKER_COMPOSE_CMD up -d
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