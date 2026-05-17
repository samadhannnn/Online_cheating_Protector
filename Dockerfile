FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Install critical system dependencies required by OpenCV and YOLO
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files into the container
COPY . .

# Expose the port that the app will run on
EXPOSE 10000

# Command to run the application using Gunicorn and Eventlet for SocketIO support
# Render dynamically injects the $PORT environment variable
CMD gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:${PORT:-10000} app:app
