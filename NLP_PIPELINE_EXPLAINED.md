# NLP Module Architecture & Execution Flow

## Overview
The NLP service processes article messages from Redis streams through a pipeline of 6 sequential components. It's designed similarly to other microservices in the Sentinel system (web-scraper, prioritiser) but focuses on extracting insights from cleaned HTML text.

**Current Status:** ✅ **WORKING** - NLP pipeline successfully processing articles as of Jan 31, 2026

---

## Critical Fixes Applied (Jan 31, 2026)

### 1. COMPOSE_PROFILES Naming Issue
**Problem:** Profile name mismatch prevented NLP-prioritiser from running
- `.env` had: `nlp_prioritiser` (underscore)
- docker-compose defined: `nlp-prioritiser` (hyphen)
- **Impact:** NLP-prioritiser never started → messages stuck in `user:to.be.nlp`

**Solution:** Fixed `.env` to use `nlp-prioritiser` (hyphen)
```bash
# Before
COMPOSE_PROFILES=ingestor,api,scraper-prioritiser,scraper,nlp_prioritiser,nlp

# After
COMPOSE_PROFILES=ingestor,api,scraper-prioritiser,scraper,nlp-prioritiser,nlp
```

### 2. Multiple Input Streams Support
**Changes:** Updated `config.py` and `main.py` to support multiple input streams
- Converts `INPUT_STREAM` string to `List[str]` via `.split(", ")`
- Allows NLP to consume from both `prioritised:to.be.nlp` and `background:to.be.nlp` if needed
- **Future-proof:** Enables handling of multiple job types simultaneously

---

## 1. Service Startup (main.py)

### Entry Point
```python
# microservices/nlp/main.py
SERVICE_NAME = "NLP"
routing_map = {
    JobType.USER.value: USER_OUTPUT_STREAM,
    JobType.BACKGROUND.value: BACKGROUND_OUTPUT_STREAM
}
config = ServiceConfig(
    routing_key=["header","type"],                      # Route based on message.header.type
    max_workers=1,                                      # Sequential execution (not concurrent)
    service_name=SERVICE_NAME,
    input_streams=INPUT_STREAM,                         # Now: ["prioritised:to.be.nlp"]
    group_name=GROUP_NAME,                              # Consumer group name
    consumer_name=CONSUMER_NAME,                        # Consumer instance name
    failure_output_stream=FAILURE_OUTPUT_STREAM,        # Where failed messages go
    routing_map=routing_map,                            # Output stream selection
    is_concurrent=False,                                # Sequential mode
    batch_size=BATCH_SIZE
)
nlp_service = NLPService(config, options=None)
nlp_service.run()
```

### Key Configuration (config.py)
```python
INPUT_STREAM_: str = get_env_var("INPUT_STREAM", str, config_logger)
INPUT_STREAM: List[str] = INPUT_STREAM_.split(", ")     # "prioritised:to.be.nlp" → ["prioritised:to.be.nlp"]

USER_OUTPUT_STREAM = "user:to.be.retrieval"             # Where user job results go
BACKGROUND_OUTPUT_STREAM = "background:to.be.stored"    # Where background job results go
FAILURE_OUTPUT_STREAM = "failure:to.be.nlp"             # Where failed jobs go

GROUP_NAME = "default"                                  # Redis consumer group
CONSUMER_NAME = "nlp-1"                                 # Consumer instance
BATCH_SIZE = 10                                         # Process up to 10 messages at once
```

---

## 2. Message Flow Architecture

### Complete Data Journey

```
┌─────────────────────────────────────────────────────────────────────┐
│                        REDIS STREAMS                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ingestor:to.be.scraped ─→ Web-Scraper ─→ prioritised:to.be.scraped│
│                                  ↓                                    │
│                          (skip if HTML provided)                      │
│                                  ↓                                    │
│                     prioritised:to.be.nlp ──────┐                   │
│                            (cleaned HTML)        │                   │
│                                                  ↓                   │
│                            ┌────────────────────────────┐            │
│                            │   NLP SERVICE (THIS)       │            │
│                            │  ┌────────────────────────┤            │
│                            │  │ 1. Preprocessor         │            │
│                            │  │ 2. Embedder             │            │
│                            │  │ 3. CentralityScorer     │            │
│                            │  │ 4. BiasDetector         │            │
│                            │  │ 5. EntityRecognizer     │            │
│                            │  │ 6. CheckWorthinessFilter│            │
│                            │  └────────────────────────┤            │
│                            └────────────────────────────┘            │
│                                    ↓                                  │
│                    ┌───────────────┴────────────────┐               │
│                    ↓                                 ↓               │
│         user:to.be.retrieval          background:to.be.stored     │
│         (User job results)            (Background job results)     │
│                                                                       │
│    If NLP fails:  failure:to.be.nlp (for manual review)            │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### Message Structure (StreamMessage)

When a message arrives in `prioritised:to.be.nlp`, it contains:
```python
{
    "redis_id": "1769838705020-0",              # Redis stream message ID
    "stream": "prioritised:to.be.nlp",          # Which stream it came from
    "data": {
        "title": "Article Title",               # From web scraper
        "text": "Cleaned HTML as text",         # From web scraper (HTML→text parsing)
        "link": "https://example.com",          # Original URL
        "header": {
            "type": "user",                     # "user" or "background" (routing key)
            "job_id": "123"
        },
        "nlp_result": None                      # Will be populated by this service
    }
}
```

---

## 3. NLP Service Orchestration (nlp_service.py)

### The ServiceTemplate Pattern

The NLPService extends `ServiceTemplate`, which provides:
- **Message Consumption**: Listens to Redis streams in batches
- **Message Parsing**: Converts raw Redis data to typed StreamMessage
- **Batch Processing**: Groups messages for efficiency
- **Error Handling**: Routes failures to a failure stream
- **Message Routing**: Directs output based on message type

### NLPService Pipeline Execution

```python
class NLPService(ServiceTemplate):
    def __init__(self, config: ServiceConfig, options: NLPOptions):
        super().__init__(config)
        
        # Pipeline components in execution order
        self.pipeline: List[NLPComponent] = [
            Preprocessor(),           # Split into sentences
            Embedder(),              # Create embeddings
            CentralityScorer(),      # Score sentence importance
            BiasDetector(),          # Detect bias/claims
            EntityRecognizer(),      # Extract named entities
            CheckWorthinessFilter()  # Rank claim worthiness
        ]
    
    def _analyze_html_and_update(self, message: StreamMessage) -> StreamMessage:
        """
        The main orchestrator that passes the article through each pipeline stage.
        """
        # 1. Create Article object from message
        article = Article(
            text=message.text,
            title=message.title,
            link=message.link
        )
        
        # 2. Create empty result object
        analysis_result = NLPResult()

        # 3. Execute each component sequentially
        for component in self.pipeline:
            try:
                component.run(article, analysis_result, self.options)
            except Exception as e:
                print(f"Pipeline error in {component.__class__.__name__}: {str(e)}")
                raise
        
        # 4. Attach results to message
        message.set_nlp_result(analysis_result)
        return message

    def _process_message(self, message: StreamMessage) -> StreamMessage:
        """Called by ServiceTemplate for each message"""
        try:
            analyzed_message = self._analyze_html_and_update(message)
            return analyzed_message
        except Exception as e:
            raise ProcessingError(f"Failed to analyze {message.link}: {e}")
```

---

## 4. Pipeline Components

### Component Base Class
```python
# microservices/nlp/models/base.py
class NLPComponent(ABC):
    @abstractmethod
    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        """
        Process article and update result object.
        """
        pass
```

### 4.1 Preprocessor
**Purpose**: Split text into sentences using NLP.

```python
class Preprocessor(NLPComponent):
    def __init__(self):
        # Load Spacy for sentence tokenization
        self.nlp = spacy.load("en_core_web_sm", disable=["ner", "tagger", "lemmatizer", "attribute_ruler"])

    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        """
        Input:  article.text = "The PM announced a new policy. It will impact the economy."
        
        Output: result.sentences = [
            SentenceScore(index=0, text="The PM announced a new policy.", score=0.0, embedding=None),
            SentenceScore(index=1, text="It will impact the economy.", score=0.0, embedding=None)
        ]
        """
        raw_text = article.text
        doc = self.nlp(raw_text.strip())
        
        sentence_objects = []
        for idx, span in enumerate(doc.sents):
            text_segment = span.text.strip()
            if not text_segment:
                continue
            
            s_obj = SentenceScore(
                index=idx,
                text=text_segment,
                score=0.0,           # Will be updated by later components
                embedding=None       # Will be filled by Embedder
            )
            sentence_objects.append(s_obj)

        result.sentences = sentence_objects
```

### 4.2 Embedder
**Purpose**: Generate vector embeddings for semantic similarity.

```python
class Embedder(NLPComponent):
    def __init__(self):
        self.model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")

    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        """
        Input:  result.sentences with text but no embeddings
        
        Output: Each sentence now has a 768-dimensional embedding vector
                Used for: deduplication, centrality scoring, semantic search
        """
        if not result.sentences:
            return

        texts = [s.text for s in result.sentences]
        embeddings = self.model.encode(texts)  # Returns numpy array

        for sentence, embedding in zip(result.sentences, embeddings):
            sentence.embedding = embedding.tolist()
```

### 4.3 CentralityScorer
**Purpose**: Identify the most important sentences (similar to TextRank).

```python
class CentralityScorer(NLPComponent):
    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        """
        Input:  result.sentences with embeddings
        
        Output: Each sentence gets a centrality score (0-1)
                Sentences similar to many others = high centrality = important
        """
        if not result.sentences or not result.sentences[0].embedding:
            return

        # Calculate similarity graph using embeddings
        # Score each sentence by its average similarity to all others
        # Higher score = more central to the article's topics
```

### 4.4 BiasDetector
**Purpose**: Identify claims and detect bias/tone using NLI model.

```python
class BiasDetector(NLPComponent):
    def __init__(self):
        self.model = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")

    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        """
        Input:  result.sentences
        
        Output: 
        - result.claims_in_article = [Claim(...), ...]  # Factual statements
        - Updates sentences with:
          - claim_type: "fact", "opinion", "question", etc.
          - confidence: 0.0-1.0 (how certain is the classification)
          - label: bias classification result
        
        Uses zero-shot classification to determine:
        - Is this sentence a factual claim or opinion?
        - What is the tone/bias?
        """
        for sentence in result.sentences:
            # Classify the sentence
            result_dict = self.model(sentence.text, ["factual claim", "opinion", "question"])
            
            sentence.claim_type = result_dict["labels"][0]
            sentence.confidence = result_dict["scores"][0]
            
            # If it's a factual claim, add to claims list
            if sentence.claim_type == "factual claim":
                claim = Claim(text=sentence.text, sentence_index=sentence.index)
                result.claims_in_article.append(claim)
```

### 4.5 EntityRecognizer (NER)
**Purpose**: Extract named entities (people, places, organizations, dates).

```python
class EntityRecognizer(NLPComponent):
    def __init__(self):
        self.model = pipeline("ner", model="dslim/bert-base-NER-uncased")

    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        """
        Input:  article.text
        
        Output: result.entities_in_article = [
            Entity(text="John Smith", entity_type="PERSON", confidence=0.95),
            Entity(text="Washington", entity_type="LOCATION", confidence=0.92),
            Entity(text="United States", entity_type="LOCATION", confidence=0.98)
        ]
        """
        # Run NER on full text
        entities = self.model(article.text)
        
        # Group by entity
        for entity in entities:
            ent_obj = Entity(
                text=entity["word"],
                entity_type=entity["entity"],
                confidence=entity["score"]
            )
            result.entities_in_article.append(ent_obj)
```

### 4.6 CheckWorthinessFilter
**Purpose**: Rank claims by their importance for fact-checking.

```python
class CheckWorthinessFilter(NLPComponent):
    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        """
        Input:  result.sentences with claim_type and result.claims_in_article
        
        Output: 
        - Rank claims by checkworthiness (0-1 score)
        - Mark sentences with is_checkworthy: bool
        - Filter out low-value claims (e.g., "is", "goes")
        
        Factors:
        - Length (too short → less worthy)
        - Contains named entities → more worthy
        - Contains numbers/dates → more worthy
        - Language patterns (avoid common phrases)
        """
        # Score each sentence for worthiness
        # Apply filters for common phrases, stopwords, etc.
```

---

## 5. Output Models

### NLPResult Structure (What Gets Stored)
```python
@dataclass
class NLPResult:
    sentences: List[SentenceScore] = field(default_factory=list)
    claims_in_article: List[Claim] = field(default_factory=list)
    entities_in_article: List[Entity] = field(default_factory=list)
    bias_profile: BiasProfile = field(default_factory=BiasProfile)

@dataclass
class SentenceScore:
    index: int                                    # Position in article
    text: str                                     # Sentence text
    score: float = 0.0                           # Centrality score
    embedding: Optional[List[float]] = None      # 768-dim vector
    label: Optional[str] = None                  # Bias label

@dataclass
class Claim:
    text: str                                     # The factual claim
    sentence_index: int                           # Where it appears
    confidence: float = 0.0                       # Confidence in classification
    checkworthy: bool = False                     # Should be fact-checked?
    entities: List[Entity] = field(default_factory=list)  # Entities involved

@dataclass
class Entity:
    text: str                                     # "John Smith"
    entity_type: str                              # "PERSON", "LOCATION", etc.
    confidence: float = 0.95                      # NER model confidence
    claims: List[int] = field(default_factory=list)  # Indices of claims mentioning this
```

---

## 6. Message Processing Cycle

### What Happens When You Send a Job

```
1. USER SUBMITS JOB via API
   └─→ /api/v1/jobs POST {"title": "...", "text": "...", "url": "..."}
   
2. API SERVICE
   └─→ Creates Article in database
   └─→ Creates Job in database with routing type "user"
   └─→ Publishes to ingestor:to.be.scraped (raw article)

3. WEB SCRAPER SERVICE
   └─→ Fetches full HTML (if no text provided)
   └─→ Parses HTML → extracts text
   └─→ Publishes enriched message to prioritised:to.be.scraped

4. PRIORITISER SERVICE
   └─→ Re-scores article by relevance/importance
   └─→ Publishes to prioritised:to.be.nlp (cleaned + scored)

5. NLP SERVICE (YOU ARE HERE)
   ├─→ Consumes from prioritised:to.be.nlp
   ├─→ Runs message through 6-component pipeline
   ├─→ Updates message with NLPResult
   │
   └─→ ROUTES RESULT based on job.header.type:
       ├─→ If "user" → publishes to user:to.be.retrieval
       │   (API retrieval service sends back to user)
       │
       └─→ If "background" → publishes to background:to.be.stored
           (Directly stored in database for search index)
```

### Processing Time
- **Preprocessor**: ~10ms (Spacy sentence split)
- **Embedder**: ~100-200ms (768-dim vectors for all sentences)
- **CentralityScorer**: ~50ms (similarity graph)
- **BiasDetector**: ~500ms (MNLI zero-shot classification)
- **EntityRecognizer**: ~100ms (NER on full text)
- **CheckWorthinessFilter**: ~50ms (ranking)
- **Total per article**: ~800ms-1.2s

---

## 7. Error Handling

### What Happens If NLP Fails

```python
def _handle_failure(self, message: StreamMessage, error: Exception):
    """
    Called by ServiceTemplate on exception
    """
    # 1. Log the error
    self.logger.error(f"Failed to process message {message.redis_id}: {error}")
    
    # 2. Publish to failure stream
    self.fail_publisher.publish_one(message.data.model_dump())
    
    # 3. Acknowledge consumed message (remove from pending)
    self.message_consumer.acknowledge(
        stream_name=message.stream,
        redis_message_id=message.redis_id
    )
    
    # Result: Message moves to failure:to.be.nlp for manual review/retry
```

---

## 8. Running Local Tests

The test pipeline can be run locally (if dependencies installed):

```bash
cd /workspaces/Sentinel
python microservices/nlp/tests/test_pipeline.py
```

This:
1. Loads article.json (test article about Iran protests)
2. Creates Article and NLPResult objects
3. Runs each component sequentially
4. Outputs analysis to test_output.json
5. Prints summary of results

---

## 9. Monitoring in Production

### Check NLP Service Logs
```bash
docker logs -f sentinel-nlp-service-container
```

Key log lines:
- `"Service 'NLPService' started. Listening on ['prioritised:to.be.nlp']."` → Ready
- `"No new messages, waiting..."` → Idle, waiting for jobs
- `"Processing batch of X messages."` → Active processing
- `"Pipeline error in ..."` → Component failed
- Timing logs show when each stage completes

### Monitor Redis Streams
```bash
redis-cli XLEN prioritised:to.be.nlp        # Messages waiting for NLP
redis-cli XLEN user:to.be.retrieval          # Results ready for API
redis-cli XLEN failure:to.be.nlp             # Failed messages
```

---

## 10. Configuration Variables

See [docker-compose.yml](docker/compose/docker-compose.yml) NLP service section:

```yaml
INPUT_STREAM: "prioritised:to.be.nlp"              # Changed from both streams
USER_OUTPUT_STREAM: "user:to.be.retrieval"
BACKGROUND_OUTPUT_STREAM: "background:to.be.stored"
FAILURE_OUTPUT_STREAM: "failure:to.be.nlp"
GROUP_NAME: "default"
CONSUMER_NAME: "nlp-1"
BATCH_SIZE: 10
NLP_MAX_WORKERS: 2
NLP_EMBEDDING_MODEL: "all-MiniLM-L6-v2"
NLP_NER_MODEL: "dslim/bert-base-NER"
NLP_BIAS_MODEL: "facebook/bart-large-mnli"
USE_GPU: "false"
```

---

## Summary

The NLP service is a **sequential text analysis pipeline** that:

1. **Consumes** messages from `prioritised:to.be.nlp`
2. **Splits** articles into sentences (Preprocessor)
3. **Vectorizes** sentences for semantic search (Embedder)
4. **Ranks** by importance (CentralityScorer)
5. **Extracts** factual claims and bias (BiasDetector)
6. **Identifies** people, places, organizations (EntityRecognizer)
7. **Scores** claims by fact-check worthiness (CheckWorthinessFilter)
8. **Routes** results based on job type (user vs background)
9. **Handles** failures gracefully (publishes to failure stream)

It integrates seamlessly with the broader Sentinel pipeline like a middleware layer that enriches articles with structured NLP insights before they're stored or served to users.
