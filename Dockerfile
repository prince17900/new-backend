# Step 1: Use an official Python runtime as a parent image
# We're using a specific version for stability.
FROM python:3.9-slim-buster

# Step 2: Set the working directory in the container
WORKDIR /app

# Step 3: Update package list and install Ghostscript
# This is where we get the permissions to install system packages.
# -y confirms all prompts, and --no-install-recommends keeps the image small.
RUN apt-get update && apt-get install -y --no-install-recommends ghostscript

# Step 4: Copy the requirements file into the container
COPY requirements.txt .

# Step 5: Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Step 6: Copy the rest of your application's code into the container
COPY . .

# Step 7: Expose the port your app runs on
# This should match the port in your app.py (e.g., 5000 or 10000 on Render)
EXPOSE 10000

# Step 8: Define the command to run your application
# Render will use this to start your Flask server.
# Gunicorn is a production-ready web server for Python.
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]
