# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy the entire project
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r backend/requirements.txt

# Change to backend directory for running the app
WORKDIR /app/backend

# Expose port (Railway will set PORT env variable)
EXPOSE 8000

# Start command
CMD uvicorn app.verifier.api:app --host 0.0.0.0 --port ${PORT:-8000}