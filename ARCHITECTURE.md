# Sentinel Backend - Complete Architecture Documentation

## 🏗️ System Overview

The Sentinel Backend is a **microservices-based misinformation intelligence platform** that ingests, processes, and analyzes news articles from RSS feeds. The system is containerized using Docker and follows a modular architecture with clear separation of concerns.

---

## 📊 Architecture Layers

### 1. Infrastructure Layer

#### PostgreSQL Database (`pgvector/pgvector:pg15`)
- **Purpose**: Primary data store with vector search capabilities
- **Port**: 15432 (external) → 5432 (internal)
- **Extensions**: pgvector for semantic search
- **Volume**: `postgres_data` for persistence
- **Health Check**: `pg_isready` with 10s interval
- **Configuration**:
  - Database: `sentinel_db`
  - User: `sentinel_user`
  - Enables vector extension via `init.sql`

#### Redis (`redis:alpine`)
- **Purpose**: Multi-purpose caching and message queue system
- **Port**: 6379
- **Volume**: `redis_data` for persistence
- **Use Cases**:
  1. **Stream-based message queues** (FIFO)
  2. **Duplicate filtering** (Set-based cache)
  3. **Result caching** (API responses)
  4. **Object caching** (not yet implemented)

---

### 2. Microservices Layer

#### A. API Gateway (`sentinel/api-gateway:1.0`)
- **Port**: 8000
- **Purpose**: Central entry point for all client requests
- **Technology**: FastAPI + Gunicorn + Uvicorn
- **Workers**: 2 (configurable via `API_WORKERS`)

**Routers**:
1. **`/health`** - Health check endpoint
2. **`/database`** - Database service status checks
3. **`/analysis`** - Article analysis orchestration
4. **`/articles`** - Article CRUD operations (placeholder)
5. **`/sources`** - RSS source management (placeholder)

**Key Operations**:
- **Analysis Orchestration**: Coordinates web scraping → NLP analysis → caching
- **Cache Management**: Checks Redis cache before processing
- **Service Coordination**: Routes requests to appropriate microservices
- **Error Handling**: Centralized error handling and logging

**Dependencies**:
```
fastapi==0.95.2
httpx==0.24.1
redis[async]==5.2.0
uvicorn==0.22.0
gunicorn==20.1.0
```

**Configuration** (`config.py`):
- Redis connection settings
- Service URLs (NLP, Web Scraper, DB Service)
- Cache TTL (3600s default)
- HTTP timeout (15s default)

---

#### B. Database Service (`sentinel/db-service:1.0`)
- **Port**: 8001
- **Purpose**: Dedicated database operations and management
- **Technology**: FastAPI + Uvicorn
- **Status**: Minimal implementation (health endpoints only)

**Current Endpoints**:
- `GET /health` - Service health check
- `GET /` - Root endpoint with version info

**Planned Features** (from DATABASE_OPERATIONS_GUIDE):
- Database CRUD operations
- Connection pooling (asyncpg)
- Repository pattern implementation
- Migration management
- Data seeding
- Health monitoring with statistics

**Dependencies**:
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
```

---

#### C. Ingestor Service (`sentinel/ingestor-service:1.0`)
- **Purpose**: Continuous RSS feed ingestion and article discovery
- **Technology**: Python + Cron + Redis
- **Schedule**: Every minute (`* * * * *`)

**Architecture**:
```
BaseIngestor (Abstract)
    ↓
RssIngestor (Implementation)
    ↓
RedisPublisher + RedisDuplicateFilter
```

**Workflow**:
1. **Fetch**: Concurrently fetch multiple RSS feeds (ThreadPoolExecutor)
2. **Parse**: Extract article metadata (link, title, summary, source)
3. **Deduplicate**: Check Redis set for previously seen URLs (1 week TTL)
4. **Filter**: Identify new articles not yet processed
5. **Publish**: Push new articles to Redis stream for web scraper
6. **Mark**: Add URLs to duplicate filter set

**RSS Sources** (`rss_feeds.json`):
- New York Times (16 feeds)
- Washington Post (4 feeds)
- Wall Street Journal (4 feeds)
- Total: 24+ news sources

**Message Format**:
```python
{
  "header": {
    "message_id": "md5_hash_of_url",
    "timestamp": "ISO_8601_datetime"
  },
  "data": {
    "url": "article_url",
    "source_rss": "rss_feed_url"
  }
}
```

**Logging**: Outputs to `/var/log/cron.log`

**Dependencies**:
```
feedparser==6.0.12
redis==6.4.0
pydantic==2.12.3
```

---

#### D. NLP Service (Not yet implemented)
- **Port**: 8000 (internal)
- **Purpose**: Natural language processing and analysis
- **Planned Features**:
  - Claim extraction
  - Sentiment analysis
  - Entity recognition
  - Embedding generation (for semantic search)

---

#### E. Web Scraper Service (Not yet implemented)
- **Port**: 8000 (internal)
- **Purpose**: Article content extraction
- **Planned Features**:
  - Full text extraction
  - Metadata parsing
  - Content cleaning

---

### 3. Common Layer (`/common`)

Shared utilities and models used across all microservices.

#### Redis Client Components:

##### A. `RedisConnection` (Singleton)
- Thread-safe singleton pattern
- Exponential retry for connection establishment
- Connection pool management
- Configuration: `REDIS_HOST`, `REDIS_PORT`

##### B. `RedisPublisher`
- Stream-based FIFO queue publishing
- Max length: 100,000 messages
- JSON serialization of messages
- Batch publishing support (`publish_many`)
- Automatic stream creation

**Operations**:
- `publish_one(message)` → Returns Redis message ID
- `publish_many(messages)` → Returns list of message IDs

##### C. `RedisConsumer`
- Consumer group-based message consumption
- Blocking/non-blocking reads
- Message acknowledgment (ACK)
- Pending entries list (PEL) management

**Operations**:
- `_create_group()` → Idempotent group creation
- `consume_one(block=0)` → Read one message
- `acknowledge(message_id)` → Mark message as processed

##### D. `RedisDuplicateFilter`
- Set-based URL deduplication
- TTL: 604,800 seconds (1 week)
- Atomic operations with pipeline
- Batch membership checks

**Operations**:
- `has_one(item)` → Check if exists
- `has_many(items)` → Filter new items
- `add_one(item)` → Add with TTL reset
- `add_many(items)` → Bulk add with TTL reset

##### E. `RedisObjectCache` (Not implemented)
- Placeholder for general object caching

---

#### Models (`/common/models`):

**Redis Models** (`api/redis_models.py`):
```python
MessageHeader: message_id, timestamp
MessageURLPayload: url, source_rss
Message: header + data
```

**Database Models**: Empty (to be implemented)
- `api/db_models.py` - Pydantic models for API
- `database/db_models.py` - SQLAlchemy models

---

#### Utilities:

**Request Utilities** (`/common/requests`):
- `@retry` decorator - Simple retry with fixed delay
- `@exponential_retry` decorator - Exponential backoff with jitter

**IO Utilities** (`/common/io`):
- `@redirect_and_modify` decorator - Capture and modify stdout
- Indent functions for log formatting

---

### 4. DevOps Layer

#### Docker Architecture:

**Base Image** (`sentinel/base-image:1.0`):
- Python 3.12-slim
- Cron installed
- Common dependencies from `core-requirements.txt`
- Shared `common/` code layer

**Layered Build Strategy**:
```
Base Image (common deps + common code)
    ↓
Service-Specific Images
    ├── API Gateway (+ httpx, redis[async])
    ├── DB Service (+ asyncpg, sqlalchemy)
    └── Ingestor (+ feedparser)
```

**Benefits**:
- Reduced build time (shared base layer)
- Consistent environment across services
- Smaller total image size

---

#### Container Orchestration (`docker-compose.yml`):

**Network**: `sentinel-net` (bridge driver)

**Service Dependencies**:
```
postgres (standalone)
redis (standalone)
    ↓
db-service (depends on: postgres, redis)
ingestor-service (depends on: postgres, redis)
```

**Volume Mounts**:
- `postgres_data` → `/var/lib/postgresql/data`
- `redis_data` → `/data`
- `db_service_logs` → `/var/log`
- `ingestor_service_logs` → `/var/log`
- `init.sql` → `/docker-entrypoint-initdb.d/init.sql`

---

#### Build & Deployment Scripts:

**`scripts/build.sh`**:
1. Prune Docker cache
2. Build base image (no cache, fresh pull)
3. Build all microservice images (no cache)

**`scripts/deploy.sh`**:
1. Tear down existing services
2. Start with `--force-recreate`
3. Follow logs

**Other Scripts**:
- `clean.sh` - Remove containers and volumes
- `clean_pycache.sh` - Remove Python cache
- `format_and_lint.sh` - Code quality
- `ingestor/` - Ingestor monitoring scripts
- `gpu/` - GPU session management (for ML)

---

## 🔄 Data Flow

### Article Ingestion Pipeline:

```
1. RSS Feeds
   ↓
2. Ingestor Service (Cron every minute)
   ├── Fetch feeds concurrently
   ├── Parse articles
   ├── Check duplicate filter
   └── Publish to Redis stream: "ingestor:to.be.scraped"
   ↓
3. [Web Scraper Service] (Consumer)
   ├── Consume from stream
   ├── Extract full content
   └── Publish to next stream
   ↓
4. [NLP Service] (Consumer)
   ├── Analyze content
   ├── Extract claims
   ├── Generate embeddings
   └── Store in PostgreSQL
   ↓
5. API Gateway
   └── Serve analysis results (cached in Redis)
```

### Analysis Request Pipeline:

```
Client → API Gateway (/analysis/analyze?url=...)
   ↓
1. Check Redis cache (key: "analysis:{sha256(url)}")
   ├── HIT → Return cached result
   └── MISS → Continue
   ↓
2. Call Web Scraper (/scrape?url=...)
   ↓
3. Call NLP Service (/analyze)
   ↓
4. Store result in Redis (TTL: 3600s)
   ↓
5. Return to client
```

---

## 🗄️ Database Schema

### Current State:
- Only pgvector extension enabled
- No tables defined yet

### Planned Schema (from DATABASE_OPERATIONS_GUIDE):

#### Sources Table:
```sql
CREATE TABLE sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    url TEXT UNIQUE NOT NULL,
    category VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### Articles Table:
```sql
CREATE TABLE articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    content TEXT,
    source_id UUID REFERENCES sources(id),
    published_at TIMESTAMP,
    analysis_status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### Article Embeddings Table (pgvector):
```sql
CREATE TABLE article_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID REFERENCES articles(id) ON DELETE CASCADE,
    embedding vector(1536),  -- OpenAI dimensions
    model_name VARCHAR(100) NOT NULL,
    embedding_type VARCHAR(50) DEFAULT 'content',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX ON article_embeddings 
USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);
```

---

## 🔧 Configuration Management

### Environment Variables (`.env`):
```bash
# PostgreSQL
POSTGRES_DB=sentinel_db
POSTGRES_USER=sentinel_user
POSTGRES_PASSWORD=your_password
POSTGRES_PORT=15432

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Services
DB_SERVICE_PORT=8001
API_GATEWAY_PORT=8000

# API
CACHE_TTL=3600
HTTP_TIMEOUT=15

# Git (for dev container)
GITHUB_USER=username
GITHUB_EMAIL=email
```

---

## 📦 Dependency Management

### Base Requirements (`docker/base/core-requirements.txt`):
- gunicorn, uvicorn (ASGI servers)
- python-dotenv (configuration)
- requests (HTTP client)
- numpy, pandas (data processing)

### Service-Specific:
- **API Gateway**: FastAPI, httpx, redis[async]
- **DB Service**: FastAPI, (asyncpg & sqlalchemy planned)
- **Ingestor**: feedparser, redis, pydantic

---

## 🚀 Current Implementation Status

### ✅ Completed:
1. Docker infrastructure (PostgreSQL + Redis)
2. Base image and build system
3. Ingestor service (RSS ingestion → Redis)
4. Redis client library (Publisher, Consumer, Duplicate Filter)
5. API Gateway skeleton with routers
6. Database service skeleton
7. Message queue architecture

### 🔨 In Progress / Planned:
1. Database models and operations
2. API endpoints for CRUD
3. Web scraper service
4. NLP service
5. Vector search (pgvector integration)
6. Connection pooling (asyncpg)
7. Repository pattern
8. Database migrations
9. Data seeding

### 📝 Not Started:
1. Authentication & authorization
2. Rate limiting
3. Monitoring & observability
4. Automated testing
5. CI/CD pipeline
6. Production deployment config

---

## 🎯 Key Design Patterns

1. **Microservices Architecture** - Service independence
2. **Message Queue Pattern** - Asynchronous processing (Redis Streams)
3. **Singleton Pattern** - Redis connection management
4. **Decorator Pattern** - Retry logic, output redirection
5. **Repository Pattern** - (Planned) Database abstraction
6. **Template Method Pattern** - BaseIngestor → RssIngestor
7. **Gateway Pattern** - API Gateway as single entry point

---

## 🔐 Security Considerations

- Credentials via environment variables
- No secrets in code
- Docker network isolation
- Health checks for service availability
- Connection retry logic for resilience

---

## 📈 Scalability Design

- **Horizontal**: Multiple ingestor instances can consume from same stream
- **Vertical**: Connection pooling for database
- **Caching**: Redis for reduced database load
- **Async**: FastAPI async endpoints
- **Queue-based**: Decoupled processing pipeline

---

## 📚 Related Documentation

- [`README.md`](./README.md) - Setup and getting started guide
- [`DATABASE_OPERATIONS_GUIDE.md`](./DATABASE_OPERATIONS_GUIDE.md) - Detailed database implementation guide
- [`docker-compose.yml`](./docker/compose/docker-compose.yml) - Container orchestration configuration

---

## 🔄 Revision History

- **2025-11-01**: Initial architecture documentation created
