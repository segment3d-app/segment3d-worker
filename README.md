# Segment3d Worker

RabbitMQ consumer for 3D gaussian splatting and segmentation pipeline.

This repository contains the RabbitMQ consumer application designed to process
videos/images through 3D gaussian splatting and segmentation pipeline. The
application listens to RabbitMQ queues for incoming tasks and processes them
using advanced algorithm for rendering and segmenting 3d scenes.

## Development

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

## Production

To run the production service, use this command to start Docker Compose:

```bash
docker compose up -d --build
```
