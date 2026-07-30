#!/bin/bash

# Test Kubernetes infrastructure
echo "Testing Kubernetes infrastructure..."

# Check if namespace exists
if kubectl get namespace ni-model &> /dev/null; then
    echo "✓ Namespace ni-model exists"
else
    echo "✗ Namespace ni-model not found"
    exit 1
fi

# Check PostgreSQL pod
if kubectl get pod -l app=postgres -n ni-model | grep -q Running; then
    echo "✓ PostgreSQL pod is running"
    
    # Test database connection
    kubectl exec -n ni-model deployment/postgres -- pg_isready -U ni_user -d ni_model
    if [ $? -eq 0 ]; then
        echo "✓ PostgreSQL accepts connections"
    else
        echo "✗ PostgreSQL connection failed"
    fi
else
    echo "✗ PostgreSQL pod not running"
fi

# Check Redis pod
if kubectl get pod -l app=redis -n ni-model | grep -q Running; then
    echo "✓ Redis pod is running"
    
    # Test Redis connection
    kubectl exec -n ni-model deployment/redis -- redis-cli ping
    if [ $? -eq 0 ]; then
        echo "✓ Redis accepts connections"
    else
        echo "✗ Redis connection failed"
    fi
else
    echo "✗ Redis pod not running"
fi

echo "Infrastructure test complete!"