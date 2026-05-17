FROM python:3.10-slim

WORKDIR /app

# Install only what opencv-python-headless actually needs
# libgl1-mesa-glx is replaced by libgl1 in newer Debian/Ubuntu
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create required directories
RUN mkdir -p database screenshots logs results models data

# Initialize database schema at build time
RUN python3 -c "from database import init_db; init_db(); print('DB initialized OK')"

EXPOSE 5001

CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--bind", "0.0.0.0:5001", "--timeout", "120", "app:app"]
