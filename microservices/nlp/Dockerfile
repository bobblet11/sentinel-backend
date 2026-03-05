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
    

RUN python3 -m spacy download en_core_web_sm
RUN python3 -c 'import torch; print(torch.cuda.is_available())'

# Pre-download all HuggingFace models into the image layer so the container
# never hits the network during startup or job processing.
RUN python3 -c "\
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, \
    AutoModelForTokenClassification, AutoModelForSequenceClassification, pipeline; \
from sentence_transformers import SentenceTransformer; \
models = [ \
    ('AutoTokenizer',                       'mrm8488/t5-base-finetuned-question-generation-ap'), \
    ('AutoModelForSeq2SeqLM',               'mrm8488/t5-base-finetuned-question-generation-ap'), \
    ('AutoTokenizer',                       'deepset/roberta-base-squad2'), \
    ('AutoModelForSeq2SeqLM',               'google/flan-t5-base'), \
    ('AutoTokenizer',                       'google/flan-t5-base'), \
    ('AutoTokenizer',                       'dslim/bert-base-NER-uncased'), \
    ('AutoModelForTokenClassification',     'dslim/bert-base-NER-uncased'), \
    ('AutoTokenizer',                       'typeform/distilbert-base-uncased-mnli'), \
    ('AutoModelForSequenceClassification',  'typeform/distilbert-base-uncased-mnli'), \
    ('AutoTokenizer',                       'cardiffnlp/twitter-roberta-base-sentiment-latest'), \
    ('AutoModelForSequenceClassification',  'cardiffnlp/twitter-roberta-base-sentiment-latest'), \
]; \
[getattr(__import__('transformers'), cls).from_pretrained(name) for cls, name in models]; \
SentenceTransformer('sentence-transformers/all-mpnet-base-v2'); \
print('All models pre-downloaded.');"

# Step 5: Copy the rest of your application's source code.
COPY microservices/nlp/ /app/microservices/nlp
COPY common/ /app/common/

# Step 7: Define the command to run your application.
CMD ["python", "-m", "microservices.nlp.main"]
