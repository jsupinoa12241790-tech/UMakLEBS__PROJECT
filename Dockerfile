FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for some packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip
RUN pip install -r /app/requirements.txt

# Copy source
COPY . /app

# Create uploads dir
RUN mkdir -p /app/static/uploads /app/generated_slips

ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production

# Run the app (Gunicorn + Eventlet for SocketIO)
CMD ["gunicorn", "-k", "eventlet", "-w", "1", "wsgi:application", "--bind", "0.0.0.0:8080"]
