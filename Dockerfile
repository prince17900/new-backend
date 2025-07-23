# Step 1: Use an official Python runtime as a parent image
FROM python:3.9-slim-bullseye

# Step 2: Set the working directory in the container
WORKDIR /app

# Step 3: Update package list and install Ghostscript
RUN apt-get update && apt-get install -y --no-install-recommends ghostscript

# Step 4: Copy the requirements file into the container
COPY requirements.txt .

# Step 5: Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Step 6: Copy the rest of your application's code into the container
COPY . .

# Step 7: Expose the port your app runs on
EXPOSE 10000

# Step 8: Define the command to run your application
# --- THIS IS THE FINAL UPDATED LINE ---
# We are forcing Gunicorn to use only 1 worker, which is crucial for low-memory environments.
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "1", "--timeout", "300", "app:app"]
