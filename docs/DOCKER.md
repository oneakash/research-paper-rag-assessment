# 🐳 Docker Deployment Guide

## Overview

This guide covers deploying the RAG system using Docker containers. The system uses a multi-container architecture with separate services for the API, database, vector store, and caching.

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│    Nginx    │───▶│   RAG App   │───▶│   Qdrant    │
│ (Reverse    │    │  (FastAPI)  │    │ (Vectors)   │
│  Proxy)     │    │             │    │             │
└─────────────┘    └─────────────┘    └─────────────┘
                          │                   │
                          ▼                   ▼
                   ┌─────────────┐    ┌─────────────┐
                   │ PostgreSQL  │    │    Redis    │
                   │ (Metadata)  │    │  (Cache)    │
                   └─────────────┘    └─────────────┘
```

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 4GB+ RAM
- 10GB+ disk space
- Google Gemini API key

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/YOUR_USERNAME/research-paper-rag-assessment.git
cd research-paper-rag-assessment
```

### 2. Configure Environment

```bash
# Copy the Docker environment template
cp .env.example .env.docker

# Edit with your settings
nano .env.docker
```

### 3. Start Services

```bash
# Start all services in background
docker-compose --env-file .env.docker up -d

# View logs
docker-compose logs -f

# Check status
docker-compose ps
```

### 4. Verify Deployment

```bash
# Check health
curl http://localhost/api/system/health

# Upload test paper
curl -X POST "http://localhost/api/papers/upload" \
  -F "file=@test_paper.pdf"

# Test query
curl -X POST "http://localhost/api/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the main topic?", "top_k": 3}'
```

## Environment Configuration

### Required Environment Variables

Create `.env.docker` with these values:

```env
# Database Configuration
POSTGRES_DB=research_papers
POSTGRES_USER=rag_user
POSTGRES_PASSWORD=secure_password_here
DATABASE_URL=postgresql://rag_user:secure_password_here@postgres:5432/research_papers

# Qdrant Vector Database
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# Redis Cache
REDIS_URL=redis://redis:6379/0

# Google Gemini API
GEMINI_API_KEY=your_real_api_key_here

# Application Settings
DEBUG=false
LOG_LEVEL=INFO
MAX_UPLOAD_SIZE=104857600  # 100MB

# Model Configuration
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
CHUNK_SIZE=512
CHUNK_OVERLAP=50

# Security
JWT_SECRET_KEY=your_jwt_secret_here
CORS_ORIGINS=["http://localhost:3000", "https://yourdomain.com"]
```

### Optional Environment Variables

```env
# Performance Tuning
MAX_WORKERS=4
WORKER_TIMEOUT=300
MAX_CONCURRENT_QUERIES=10

# Monitoring
ENABLE_METRICS=true
METRICS_PORT=9090

# Backup
BACKUP_SCHEDULE=0 2 * * *  # Daily at 2 AM
BACKUP_RETENTION_DAYS=30
```

## Service Configuration

### Database (PostgreSQL)

```yaml
postgres:
  image: postgres:15-alpine
  environment:
    POSTGRES_DB: ${POSTGRES_DB}
    POSTGRES_USER: ${POSTGRES_USER}
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
  volumes:
    - postgres_data:/var/lib/postgresql/data
    - ./init.sql:/docker-entrypoint-initdb.d/init.sql
  ports:
    - "5432:5432"
  restart: unless-stopped
```

**Configuration Options:**

- `shared_buffers`: 256MB (adjust based on RAM)
- `max_connections`: 100
- `work_mem`: 4MB

### Vector Database (Qdrant)

```yaml
qdrant:
  image: qdrant/qdrant:latest
  ports:
    - "6333:6333"
    - "6334:6334"
  volumes:
    - qdrant_data:/qdrant/storage
  environment:
    QDRANT__SERVICE__HTTP_PORT: 6333
    QDRANT__SERVICE__GRPC_PORT: 6334
    QDRANT__STORAGE__PERFORMANCE__MAX_SEARCH_THREADS: 4
```

**Performance Tuning:**

```yaml
environment:
  QDRANT__STORAGE__PERFORMANCE__MAX_SEARCH_THREADS: 4
  QDRANT__STORAGE__OPTIMIZERS__DEFAULT_SEGMENT_NUMBER: 2
  QDRANT__STORAGE__WAL__WAL_CAPACITY_MB: 64
```

### Cache (Redis)

```yaml
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
  volumes:
    - redis_data:/data
  command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
```

### Main Application

```yaml
rag-app:
  build:
    context: .
    dockerfile: Dockerfile
  ports:
    - "8000:8000"
  environment:
    DATABASE_URL: ${DATABASE_URL}
    QDRANT_HOST: qdrant
    REDIS_URL: redis://redis:6379/0
    GEMINI_API_KEY: ${GEMINI_API_KEY}
  volumes:
    - ./uploads:/app/uploads
    - ./papers:/app/papers
    - ./logs:/app/logs
  depends_on:
    postgres:
      condition: service_healthy
    qdrant:
      condition: service_healthy
    redis:
      condition: service_healthy
```

## Production Deployment

### 1. Production Docker Compose

```yaml
# docker-compose.prod.yml
version: "3.8"

services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.prod.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
      - ./logs/nginx:/var/log/nginx
    depends_on:
      - rag-app
    restart: unless-stopped

  rag-app:
    build:
      context: .
      dockerfile: Dockerfile.prod
    environment:
      DEBUG: false
      LOG_LEVEL: WARNING
      WORKERS: 4
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 2G
          cpus: "1"
        reservations:
          memory: 1G
          cpus: "0.5"
    restart: unless-stopped

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: "0.5"
    restart: unless-stopped

  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - qdrant_data:/qdrant/storage
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: "1"
    restart: unless-stopped

volumes:
  postgres_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/postgres
  qdrant_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/qdrant
```

### 2. SSL Configuration

```nginx
# nginx.prod.conf
events {
    worker_connections 1024;
}

http {
    upstream rag_backend {
        least_conn;
        server rag-app:8000 max_fails=3 fail_timeout=30s;
    }

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=upload:10m rate=1r/s;

    server {
        listen 80;
        server_name yourdomain.com;
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name yourdomain.com;

        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;

        client_max_body_size 100M;

        # API endpoints with rate limiting
        location /api/ {
            limit_req zone=api burst=20 nodelay;
            proxy_pass http://rag_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_timeout 300s;
        }

        # Upload endpoints with stricter rate limiting
        location /api/papers/upload {
            limit_req zone=upload burst=5 nodelay;
            proxy_pass http://rag_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_timeout 600s;
        }
    }
}
```

### 3. Production Dockerfile

```dockerfile
# Dockerfile.prod
FROM python:3.11-slim as builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim as production

WORKDIR /app

# Security: Create non-root user
RUN groupadd -r rag && useradd -r -g rag rag

# Install runtime dependencies
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy installed packages
COPY --from=builder /root/.local /home/rag/.local

# Copy application
COPY --chown=rag:rag src/ ./src/

# Create directories
RUN mkdir -p uploads papers logs && chown -R rag:rag uploads papers logs

# Switch to non-root user
USER rag

# Update PATH
ENV PATH=/home/rag/.local/bin:$PATH

EXPOSE 8000

# Use gunicorn for production
CMD ["gunicorn", "src.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
```

## Management Commands

### Start Services

```bash
# Development
docker-compose -f docker-compose.dev.yml up -d

# Production
docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

### Monitor Services

```bash
# View all logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f rag-app
docker-compose logs -f postgres

# Monitor resources
docker stats

# Health checks
docker-compose ps
```

### Scaling

```bash
# Scale API instances
docker-compose up -d --scale rag-app=3

# Scale with resource limits
docker-compose -f docker-compose.prod.yml up -d --scale rag-app=4
```

### Backup and Restore

```bash
# Database backup
docker-compose exec postgres pg_dump -U rag_user research_papers > backup.sql

# Qdrant backup
docker-compose exec qdrant /qdrant/qdrant --uri http://localhost:6333 backup create

# Restore database
docker-compose exec -T postgres psql -U rag_user research_papers < backup.sql
```

### Maintenance

```bash
# Update images
docker-compose pull
docker-compose up -d

# Clean up
docker system prune -f
docker volume prune -f

# View disk usage
docker system df
```

## Monitoring and Logging

### Application Metrics

```yaml
# Add to docker-compose.yml
prometheus:
  image: prom/prometheus
  ports:
    - "9090:9090"
  volumes:
    - ./prometheus.yml:/etc/prometheus/prometheus.yml

grafana:
  image: grafana/grafana
  ports:
    - "3000:3000"
  environment:
    GF_SECURITY_ADMIN_PASSWORD: admin
  volumes:
    - grafana_data:/var/lib/grafana
```

### Log Management

```yaml
# Centralized logging
elasticsearch:
  image: elasticsearch:7.15.0
  environment:
    discovery.type: single-node
  ports:
    - "9200:9200"

kibana:
  image: kibana:7.15.0
  ports:
    - "5601:5601"
  depends_on:
    - elasticsearch
```

## Troubleshooting

### Common Issues

**Service won't start:**

```bash
# Check logs
docker-compose logs service-name

# Check resources
docker system df
free -h

# Restart specific service
docker-compose restart rag-app
```

**Database connection issues:**

```bash
# Test database connectivity
docker-compose exec rag-app python -c "
import psycopg2
conn = psycopg2.connect('postgresql://rag_user:password@postgres:5432/research_papers')
print('Connected successfully')
"
```

**Qdrant connection issues:**

```bash
# Test Qdrant
docker-compose exec rag-app curl http://qdrant:6333/collections
```

**Memory issues:**

```bash
# Check memory usage
docker stats --no-stream

# Increase memory limits in docker-compose.yml
deploy:
  resources:
    limits:
      memory: 4G
```

### Performance Tuning

**Database optimization:**

```sql
-- Connect to database
docker-compose exec postgres psql -U rag_user research_papers

-- Check performance
SELECT * FROM pg_stat_activity;

-- Optimize queries
EXPLAIN ANALYZE SELECT * FROM papers WHERE title ILIKE '%keyword%';
```

**Qdrant optimization:**

```bash
# Check Qdrant metrics
curl http://localhost:6333/metrics

# Optimize collection
curl -X PUT http://localhost:6333/collections/research_papers/index \
  -H "Content-Type: application/json" \
  -d '{"field_name": "paper_id", "field_schema": "integer"}'
```

## Security Considerations

### Network Security

```yaml
# Restrict network access
networks:
  internal:
    driver: bridge
    internal: true
  external:
    driver: bridge

services:
  rag-app:
    networks:
      - internal
      - external

  postgres:
    networks:
      - internal # Only internal access
```

### Secrets Management

```bash
# Use Docker secrets in production
echo "secure_password" | docker secret create db_password -

# Reference in compose file
services:
  postgres:
    secrets:
      - db_password
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
```

### SSL Certificates

```bash
# Generate self-signed certificate for testing
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/key.pem -out ssl/cert.pem

# For production, use Let's Encrypt
certbot certonly --webroot -w /var/www/html -d yourdomain.com
```

This Docker deployment guide provides everything needed for both development and production deployments of your RAG system.
