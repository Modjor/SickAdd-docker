# Use a lightweight Python image
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy the requirements.txt file and scripts into the working directory
COPY requirements.txt SickAdd.py launcher.py /app/

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set the environment variables
ENV WATCHLIST_URLS=https://www.imdb.com/list/ls00000000
ENV SICKCHILL_URL=http://192.168.1.2:8081
ENV SICKCHILL_API_KEY=1a2b3c4d5e6f7g8h
ENV INTERVAL_MINUTES=1440
ENV DEBUG_ENABLED=true

# Launch the intermediate script
CMD ["python", "launcher.py"]
