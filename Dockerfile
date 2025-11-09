# Python base image
FROM python:3.10-slim

# Set environment variables to prevent generating .pyc files and to run Python in unbuffered mode
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Install dependencies
# Copy the requirements file first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code
COPY . .
