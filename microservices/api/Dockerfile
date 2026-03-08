FROM sentinel/python-light-common:3.12

WORKDIR /app

COPY microservices/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY microservices/api /app/microservices/api

EXPOSE 8001

# Run the application
CMD ["python", "-m", "microservices.api.app.main"]
