# Deployment Guide

## Overview

This guide covers deploying the Mental Health Platform to production using Docker, Kubernetes, or cloud services.

---

## Pre-Deployment Checklist

- [ ] All tests passing (80%+ backend, 60%+ frontend)
- [ ] Security scans passed (Bandit, npm audit)
- [ ] Docker images built and pushed to registry
- [ ] Environment variables configured
- [ ] Database backups in place
- [ ] SSL/TLS certificates ready
- [ ] Monitoring and logging configured
- [ ] Incident response plan documented

---

## Environment Setup

### Required Environment Variables

**Backend** (`.env`):

```bash
# Database
DATABASE_AUTH_URL=postgresql+asyncpg://user:pass@host:5432/auth_db
DATABASE_PLATFORM_URL=postgresql+asyncpg://user:pass@host:5433/platform_db

# Redis
REDIS_URL=redis://localhost:6379

# Security
JWT_SECRET=your-very-long-random-secret-key-min-32-chars
AES_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef

# SSO
OIDC_CLIENT_ID=your-client-id
OIDC_CLIENT_SECRET=your-client-secret
OIDC_AUTHORITY_URL=https://sso.university.edu
OIDC_REDIRECT_URI=https://mindbridge.university.edu/sso/callback

# CORS
CORS_ORIGINS=https://mindbridge.university.edu,https://www.mindbridge.university.edu

# Email (optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# Debug
DEBUG=False
LOG_LEVEL=INFO
```

**Frontend** (`.env`):

```bash
VITE_API_URL=https://api.mindbridge.university.edu/api/v1
VITE_APP_NAME=MindBridge
```

---

## Docker Deployment (Single Host)

### Build Images

```bash
# Build backend
docker build -f backend/Dockerfile -t mental-health-backend:1.0.0 .

# Build frontend
docker build -f frontend/Dockerfile -t mental-health-frontend:1.0.0 ./frontend

# Tag for registry
docker tag mental-health-backend:1.0.0 your-registry/mental-health-backend:1.0.0
docker tag mental-health-frontend:1.0.0 your-registry/mental-health-frontend:1.0.0

# Push to registry
docker push your-registry/mental-health-backend:1.0.0
docker push your-registry/mental-health-frontend:1.0.0
```

### Docker Compose (Production)

**File**: `docker-compose.prod.yml`

```yaml
version: "3.9"

services:
  # PostgreSQL Auth Database
  auth_db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${DB_AUTH_USER}
      POSTGRES_PASSWORD: ${DB_AUTH_PASSWORD}
      POSTGRES_DB: auth_db
    volumes:
      - auth_db_data:/var/lib/postgresql/data
      - ./backups:/backups
    restart: always
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_AUTH_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  # PostgreSQL Platform Database
  platform_db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${DB_PLATFORM_USER}
      POSTGRES_PASSWORD: ${DB_PLATFORM_PASSWORD}
      POSTGRES_DB: platform_db
    volumes:
      - platform_db_data:/var/lib/postgresql/data
      - ./backups:/backups
    restart: always
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_PLATFORM_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Redis Cache
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    restart: always
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # FastAPI Backend
  backend:
    image: your-registry/mental-health-backend:1.0.0
    environment:
      DATABASE_AUTH_URL: ${DATABASE_AUTH_URL}
      DATABASE_PLATFORM_URL: ${DATABASE_PLATFORM_URL}
      REDIS_URL: ${REDIS_URL}
      JWT_SECRET: ${JWT_SECRET}
      AES_KEY: ${AES_KEY}
      DEBUG: "False"
    depends_on:
      auth_db:
        condition: service_healthy
      platform_db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: always
    ports:
      - "8000:8000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    volumes:
      - ./logs:/app/logs

  # Celery Worker
  celery_worker:
    image: your-registry/mental-health-backend:1.0.0
    command: celery -A backend.tasks.celery_app worker --loglevel=info
    environment:
      DATABASE_AUTH_URL: ${DATABASE_AUTH_URL}
      DATABASE_PLATFORM_URL: ${DATABASE_PLATFORM_URL}
      REDIS_URL: ${REDIS_URL}
    depends_on:
      - backend
      - redis
    restart: always

  # Celery Beat Scheduler
  celery_beat:
    image: your-registry/mental-health-backend:1.0.0
    command: celery -A backend.tasks.celery_app beat --loglevel=info
    environment:
      DATABASE_AUTH_URL: ${DATABASE_AUTH_URL}
      DATABASE_PLATFORM_URL: ${DATABASE_PLATFORM_URL}
      REDIS_URL: ${REDIS_URL}
    depends_on:
      - backend
      - redis
    restart: always

  # React Frontend
  frontend:
    image: your-registry/mental-health-frontend:1.0.0
    environment:
      VITE_API_URL: ${API_URL}
    depends_on:
      - backend
    restart: always
    ports:
      - "80:80"
      - "443:443"

  # Nginx Reverse Proxy
  nginx:
    image: nginx:alpine
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/nginx/certs:ro
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - frontend
      - backend
    restart: always

volumes:
  auth_db_data:
  platform_db_data:
  redis_data:
```

### Start Production Stack

```bash
# Load environment
export $(cat .env.prod | xargs)

# Start services
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.prod.yml logs -f backend

# Stop services
docker-compose -f docker-compose.prod.yml down
```

---

## Kubernetes Deployment

### Prerequisites

- Kubernetes cluster (1.24+)
- kubectl configured
- Container registry (Docker Hub, AWS ECR, GCR, etc.)
- Helm (optional, for package management)

### Create Namespace

```bash
kubectl create namespace mindbridge
kubectl config set-context --current --namespace=mindbridge
```

### Create ConfigMaps & Secrets

```bash
# Create secret for sensitive data
kubectl create secret generic mindbridge-secrets \
  --from-literal=jwt-secret="your-jwt-secret" \
  --from-literal=aes-key="your-aes-key" \
  --from-literal=db-auth-password="auth-db-password" \
  --from-literal=db-platform-password="platform-db-password"

# Create configmap for application config
kubectl create configmap mindbridge-config \
  --from-literal=debug="false" \
  --from-literal=log-level="INFO"
```

### Database Deployments

**File**: `k8s/postgres-deployment.yaml`

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: auth-db-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: auth-db
spec:
  replicas: 1
  selector:
    matchLabels:
      app: auth-db
  template:
    metadata:
      labels:
        app: auth-db
    spec:
      containers:
        - name: postgres
          image: postgres:16-alpine
          ports:
            - containerPort: 5432
          env:
            - name: POSTGRES_DB
              value: auth_db
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: mindbridge-secrets
                  key: db-auth-password
          volumeMounts:
            - name: storage
              mountPath: /var/lib/postgresql/data
      volumes:
        - name: storage
          persistentVolumeClaim:
            claimName: auth-db-pvc

---
apiVersion: v1
kind: Service
metadata:
  name: auth-db
spec:
  selector:
    app: auth-db
  ports:
    - port: 5432
      targetPort: 5432
  type: ClusterIP
```

### Backend Deployment

**File**: `k8s/backend-deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      containers:
        - name: backend
          image: your-registry/mental-health-backend:1.0.0
          imagePullPolicy: Always
          ports:
            - containerPort: 8000
          env:
            - name: DATABASE_AUTH_URL
              value: postgresql+asyncpg://postgres:$(DB_AUTH_PASSWORD)@auth-db:5432/auth_db
              valueFrom:
                secretKeyRef:
                  name: mindbridge-secrets
                  key: db-auth-password
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5

---
apiVersion: v1
kind: Service
metadata:
  name: backend-service
spec:
  selector:
    app: backend
  ports:
    - port: 80
      targetPort: 8000
  type: LoadBalancer
```

### Deploy to Kubernetes

```bash
# Create all resources
kubectl apply -f k8s/

# Check status
kubectl get pods
kubectl get services

# View logs
kubectl logs -f deployment/backend

# Scale deployment
kubectl scale deployment backend --replicas=5

# Update image
kubectl set image deployment/backend backend=your-registry/mental-health-backend:1.1.0

# Check rollout status
kubectl rollout status deployment/backend
```

---

## Cloud Deployment Options

### AWS ECS/Fargate

1. Create ECR repositories
2. Push Docker images
3. Define ECS task definitions
4. Create ECS services
5. Configure load balancer
6. Set up RDS databases

### Google Cloud Run

```bash
# Deploy backend
gcloud run deploy mindbridge-backend \
  --image your-registry/mental-health-backend:1.0.0 \
  --platform managed \
  --region us-central1 \
  --set-env-vars DATABASE_AUTH_URL=... \
  --memory 512M \
  --cpu 1

# Deploy frontend
gcloud run deploy mindbridge-frontend \
  --image your-registry/mental-health-frontend:1.0.0 \
  --platform managed \
  --region us-central1 \
  --memory 256M
```

### Azure Container Instances

```bash
# Deploy container
az container create \
  --resource-group mindbridge \
  --name mindbridge-backend \
  --image your-registry/mental-health-backend:1.0.0 \
  --ports 8000 \
  --cpu 1 \
  --memory 0.5 \
  --environment-variables DATABASE_AUTH_URL=...
```

---

## SSL/TLS Setup

### Using Let's Encrypt with Nginx

**File**: `nginx.conf`

```nginx
server {
    listen 80;
    server_name mindbridge.university.edu;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name mindbridge.university.edu;

    ssl_certificate /etc/letsencrypt/live/mindbridge.university.edu/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mindbridge.university.edu/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Frontend
    location / {
        proxy_pass http://frontend:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # API
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

---

## Database Backup & Recovery

### Backup Strategy

```bash
#!/bin/bash
# backup.sh

# Backup auth database
docker-compose exec -T auth_db pg_dump -U postgres auth_db > backups/auth_db_$(date +%Y%m%d_%H%M%S).sql

# Backup platform database
docker-compose exec -T platform_db pg_dump -U postgres platform_db > backups/platform_db_$(date +%Y%m%d_%H%M%S).sql

# Backup Redis
docker-compose exec -T redis redis-cli BGSAVE
docker cp $(docker-compose ps -q redis):/data/dump.rdb backups/redis_$(date +%Y%m%d_%H%M%S).rdb
```

### Recovery

```bash
# Restore auth database
docker-compose exec -T auth_db psql -U postgres auth_db < backups/auth_db_20260601_120000.sql

# Restore platform database
docker-compose exec -T platform_db psql -U postgres platform_db < backups/platform_db_20260601_120000.sql
```

---

## Monitoring & Logging

### Health Checks

```bash
# API health
curl http://localhost:8000/health

# Readiness probe
curl http://localhost:8000/health/ready

# Database check
curl http://localhost:8000/health/ready?detailed=true
```

### Centralized Logging (ELK Stack)

```yaml
# docker-compose addition
elasticsearch:
  image: docker.elastic.co/elasticsearch/elasticsearch:8.0.0
  environment:
    - discovery.type=single-node
  ports:
    - "9200:9200"

kibana:
  image: docker.elastic.co/kibana/kibana:8.0.0
  ports:
    - "5601:5601"

logstash:
  image: docker.elastic.co/logstash/logstash:8.0.0
  volumes:
    - ./logstash.conf:/usr/share/logstash/pipeline/logstash.conf
```

---

## Performance Tuning

### Database Connection Pooling

```python
# backend/core/database.py
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    echo_pool=False,
)
```

### Celery Task Tuning

```python
# backend/tasks/celery_config.py
CELERY_WORKER_PREFETCH_MULTIPLIER = 4
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000
CELERY_BROKER_POOL_LIMIT = 1
```

### Redis Optimization

```bash
# Production Redis settings
maxmemory 2gb
maxmemory-policy allkeys-lru
save ""  # Disable RDB for speed
appendonly yes
```

---

## Disaster Recovery

### RTO/RPO Targets

- **RTO** (Recovery Time Objective): 1 hour
- **RPO** (Recovery Point Objective): 15 minutes

### Failover Procedure

1. Detect failure (health check fails)
2. Promote standby database (if using replication)
3. Update DNS to standby instance
4. Restart services
5. Verify functionality
6. Investigate root cause

---

## Rollback Procedure

```bash
# If new version has issues

# With Docker Compose
docker-compose -f docker-compose.prod.yml set-image backend=your-registry/mental-health-backend:1.0.0-previous
docker-compose -f docker-compose.prod.yml up -d

# With Kubernetes
kubectl rollout undo deployment/backend
kubectl rollout status deployment/backend
```

---

## Post-Deployment Checklist

- [ ] All services running and healthy
- [ ] Databases migrated successfully
- [ ] SSL/TLS working correctly
- [ ] Health checks passing
- [ ] Logs aggregating properly
- [ ] Monitoring alerts configured
- [ ] Backup jobs running
- [ ] Team notified
- [ ] Status page updated
- [ ] Runbook documented

---

**Status**: ✅ Deployment Guide Complete  
**Recommended**: Start with Docker Compose, scale to Kubernetes as needed
