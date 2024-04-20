#!/bin/bash

# Exit script on error
set -e

# Build and push Docker image in one step
echo "Building and pushing Docker image to Docker Hub..."
docker build -t marcellinoco/segment3d:segment3d-worker .
docker push marcellinoco/segment3d:segment3d-worker
