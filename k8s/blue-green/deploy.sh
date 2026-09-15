#!/bin/bash
# Blue-Green Deployment Script for FaceDeep
# Usage: ./deploy-blue-green.sh <image_tag>

set -e

IMAGE_TAG=${1:-"latest"}
NAMESPACE="facedeep"

echo "=== Blue-Green Deployment ==="
echo "Image tag: $IMAGE_TAG"

# Determine current active color
CURRENT_COLOR=$(kubectl get svc facedeep -n $NAMESPACE -o jsonpath='{.spec.selector.track}' 2>/dev/null || echo "blue")
echo "Current active: $CURRENT_COLOR"

# Set target color
if [ "$CURRENT_COLOR" = "blue" ]; then
    TARGET_COLOR="green"
else
    TARGET_COLOR="blue"
fi
echo "Deploying to: $TARGET_COLOR"

# Update the inactive deployment
echo "Updating facedeep-$TARGET_COLOR deployment..."
kubectl set image deployment/facedeep-$TARGET_COLOR \
    api=facedeep:$IMAGE_TAG \
    -n $NAMESPACE

# Wait for rollout
echo "Waiting for rollout..."
kubectl rollout status deployment/facedeep-$TARGET_COLOR -n $NAMESPACE --timeout=300s

# Health check
echo "Running health check..."
kubectl exec -n $NAMESPACE deployment/facedeep-$TARGET_COLOR -- \
    curl -sf http://localhost:8000/api/v2/health || {
        echo "Health check failed! Rolling back."
        kubectl rollout undo deployment/facedeep-$TARGET_COLOR -n $NAMESPACE
        exit 1
    }

# Switch traffic
echo "Switching traffic to $TARGET_COLOR..."
kubectl patch svc facedeep -n $NAMESPACE -p "{\"spec\":{\"selector\":{\"track\":\"$TARGET_COLOR\"}}}"

# Scale down old
echo "Scaling down facedeep-$CURRENT_COLOR..."
kubectl scale deployment/facedeep-$CURRENT_COLOR --replicas=0 -n $NAMESPACE

echo "=== Deployment complete ==="
echo "Active: $TARGET_COLOR"
echo "Inactive: $CURRENT_COLOR (scaled to 0)"
