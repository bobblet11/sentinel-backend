ARG BASE_IMAGE
FROM $BASE_IMAGE

WORKDIR /app

COPY microservices/retrieval_layer/requirements.txt .

RUN apt-get update && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN python3 -c 'import torch; print(torch.cuda.is_available())'

COPY microservices/retrieval_layer /app/microservices/retrieval_layer

CMD ["python", "-m", "microservices.retrieval_layer.main"]

