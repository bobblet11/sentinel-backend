FROM sentinel/python-light:3.12

WORKDIR /app

# CPU PyTorch (~400MB vs 2GB+ CUDA)
RUN pip install --no-cache-dir \
    "torch==2.6.0" "torchvision==0.21.0" "torchaudio==2.6.0" --index-url https://download.pytorch.org/whl/cpu

# nlp packages
COPY docker/base/core-nlp-requirements.txt .
RUN pip install --no-cache-dir \
    -r core-nlp-requirements.txt \
    && rm -rf core-nlp-requirements.txt

RUN pip install --no-cache-dir "pip<25"

RUN python -m spacy download en_core_web_sm

# common packages
COPY common/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && rm -rf requirements.txt

COPY common/ /app/common/
