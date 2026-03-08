FROM sentinel/python-light:3.12
COPY common/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && rm -rf requirements.txt

COPY common/ /app/common/
