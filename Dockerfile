# Dockerfile

# Use the official Python image
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN apt update && apt install libmagicwand-dev && pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Expose port 
EXPOSE 5002

# Command to run the app with Gunicorn
CMD ["gunicorn", "--config", "gunicorn.py", "app:app"]
