FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py ./
COPY config.json.template ./

# Create data directory for cache.db and config persistence
RUN mkdir -p /app/data

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command - run the daily update
CMD ["python", "main.py"]