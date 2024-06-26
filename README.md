# Segment3d Worker

RabbitMQ consumer for 3D gaussian splatting and segmentation pipeline.

This repository contains the RabbitMQ consumer application designed to process
videos/images through 3D gaussian splatting and segmentation pipeline. The
application listens to RabbitMQ queues for incoming tasks and processes them
using advanced algorithm for rendering and segmenting 3d scenes.

## Cloning the repository

This repository contains submodules, thus please clone with:

```bash
git clone https://github.com/segment3d-app/segment3d-worker --recursive
git submodule update --init --recursive
```

## Environment Variables

Variables will be read from the `.env` file. Make sure to insert the correct
values.

On your first setup, duplicate the env template:

```bash
cp .env.example .env
```

## Development

This section will show 2 options for running the service in development mode.

### Manual Run

Before development, prepare a Python virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Then install the required dependencies:

```bash
pip install -r requirements.txt
```

Then run the entry script:

```bash
python main.py
```

### Docker Compose

Another option is to use start the service with Docker Compose:

```bash
docker compose up -d --build
```

## Production Build

When everything is done and tested on local, we can publish the docker image
to a registry. The easiest (and cheapest) registry is the
[Docker Hub](https://hub.docker.com). We can then pull the image from any
machine (including Kubernetes).

In this section, we provide 2 approaches to build and push image to registry.

### Single-platform Build

Build and push the docker image:

```bash
# Namespace: <USERNAME>/<REPOSITORY>:<TAG>
docker build -t marcellinoco/segment3d:segment3d-worker .
docker push marcellinoco/segment3d:segment3d-worker
```

Or you can use the utility script:

```bash
sh ./scripts/build.sh
```

### Multiplatform Build

Build and push the docker image with multiplatform builder:

```bash
# Setup multiplatform docker builder
docker buildx create --name multiarch-builder --driver docker-container --use
docker buildx inspect --bootstrap

# Build and push docker image
docker buildx build --platform linux/amd64,linux/arm64 -t marcellinoco/segment3d:segment3d-worker --push .
```

Or you can use the utility script:

```bash
sh ./scripts/build-multiplatform.sh
```

## Production Deployment

To run the service inside Kubernetes, the manifest file is in
`segment3d-worker.yaml`.

First, setup the configmap for environment variables:

```bash
kubectl create configmap segment3d-worker-configmap --from-env-file=.env
```

Then, run the containers:

```bash
kubectl apply -f manifest.yaml
```
