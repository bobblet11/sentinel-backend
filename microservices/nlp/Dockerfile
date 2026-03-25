ARG BASE_IMAGE
FROM $BASE_IMAGE

WORKDIR /app

COPY microservices/nlp/requirements.txt .

RUN apt-get update && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
    
RUN python3 -c 'import torch; print(torch.cuda.is_available())'

COPY microservices/nlp/ /app/microservices/nlp/

CMD ["python", "-m", "microservices.nlp.main"]
