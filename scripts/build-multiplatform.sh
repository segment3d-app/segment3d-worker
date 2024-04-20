#!/bin/bash

# Exit script on error
set -e

# Step 1: Setup multiplatform Docker builder
echo "Setting up multiplatform Docker builder..."
docker buildx create --name multiarch-builder --driver docker-container --use
docker buildx inspect --bootstrap

# Step 2: Build and push Docker image
echo "Building and pushing Docker image to Docker Hub..."
docker buildx build --platform linux/amd64,linux/arm64 -t marcellinoco/segment3d:segment3d-worker --push .
