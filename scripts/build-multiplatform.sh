#!/bin/bash

# Exit script on error
set -e

# Check if the multiarch builder exists
if ! docker buildx ls | grep -q multiarch-builder; then
  echo "Creating new multiarch builder..."
  docker buildx create --name multiarch-builder --driver docker-container --use
else
  echo "Using existing multiarch builder..."
  docker buildx use multiarch-builder
fi

# Ensure the builder is running
docker buildx inspect --bootstrap

# Build and push Docker image for multiple platforms
echo "Building and pushing Docker image for multiple platforms..."
docker buildx build --platform linux/amd64,linux/arm64 -t marcellinoco/segment3d:segment3d-worker --push .
