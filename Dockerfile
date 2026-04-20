FROM python:3.10-slim

WORKDIR /app

# Install basic system dependencies
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Use opencv-python-headless to avoid GUI dependencies in a container
RUN pip install --no-cache-dir qrcode[pil] pillow numpy opencv-python-headless paho-mqtt flask

COPY . .
RUN mkdir -p /app/outputs

CMD ["python", "core/orchestrator.py"]
