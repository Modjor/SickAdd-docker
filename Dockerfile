# Use a lightweight Python image
FROM python:3.9-alpine

# Set the working directory
WORKDIR /app

# Copy the requirements.txt file and scripts into the working directory
COPY requirements.txt SickAdd.py launcher.py /app/

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set the environment variables
ENV WATCHLIST_URLS=https://www.imdb.com/list/ls00000000
ENV SICKCHILL_URL=http://sickchill_server_ip:port
ENV SICKCHILL_API_KEY=your_sickchill_api_key
ENV INTERVAL_MINUTES=1440
ENV DATABASE_PATH=/var/sickadd.db
ENV DEBUG_LOG_PATH=/var/sickadd.log
ENV DEBUG_ENABLED=1
ENV DEBUG_MAX_SIZE_MB=100

# Launch the intermediate script
CMD ["python", "launcher.py"]
