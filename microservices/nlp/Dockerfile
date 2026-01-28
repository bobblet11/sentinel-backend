# Step 1: Start from our base image
FROM sentinel/base-image:1.0

# Step 2: Set a working directory inside the container.
WORKDIR /app

# Step 3: Copy the dependencies file first.
COPY microservices/nlp/requirements.txt .

# Step 4: Install cron and python packages
RUN apt-get update && apt-get install -y cron && \
    pip install --no-cache-dir -r requirements.txt && \
    python -m spacy download en_core_web_sm && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
    
# Step 5: Copy the rest of your application's source code.
COPY microservices/nlp/ /app/microservices/nlp

# Step 7: Define the command to run your application.
CMD ["python", "-m", "microservices.nlp.main"]
