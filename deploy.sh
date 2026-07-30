#!/bin/bash

# Deploy NI Model to Kubernetes
echo "Deploying NI Model to Kubernetes..."

# Apply namespace
kubectl apply -f k8s/namespace.yaml

# Apply database and cache
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml

# Wait for database to be ready
echo "Waiting for PostgreSQL to be ready..."
kubectl wait --for=condition=ready pod -l app=postgres -n ni-model --timeout=300s

echo "Waiting for Redis to be ready..."
kubectl wait --for=condition=ready pod -l app=redis -n ni-model --timeout=300s

# Build and deploy app (requires Docker image to be built first)
echo "Note: Build Docker image with 'docker build -t ni-model:latest .'"
echo "Then apply app deployment:"
echo "kubectl apply -f k8s/app.yaml"

echo "Deployment complete!"
echo "Check status with: kubectl get pods -n ni-model"