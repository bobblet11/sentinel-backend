FROM sentinel/base-image:1.1

WORKDIR /app

COPY microservices/retrieval_layer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY microservices/retrieval_layer /app/microservices/retrieval_layer
COPY common/ /app/common/


CMD ["python", "-m", "microservices.retrieval_layer.main"]
# CMD ["tail", "-f", "/dev/null"]
