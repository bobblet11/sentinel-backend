# Database Operations Guide

This guide details how to proceed with database operations, scaling, and integration for the Sentinel PostgreSQL service.

## 📋 Table of Contents

1. [Database Management](#database-management)
2. [Defining Models](#defining-models)
3. [Defining Endpoints](#defining-endpoints)
4. [Core Database Services](#core-database-services)
5. [pgvector Integration](#pgvector-integration)
6. [Best Practices](#best-practices)

---

## 🗄️ Database Management

### Running the Database

#### **Just the database:**
```bash
# Start PostgreSQL container
docker compose up postgres -d

# Start database service
docker compose up db-service -d

# Check status by calling the database service's API
curl http://localhost:8000/database/status
```

#### **Changing Ports:**

1. **Update `.env` file:**
   ```bash
   # Change external port (currently 15432)
   POSTGRES_PORT=15433
   
   # Change database service port (currently 8001)
   DB_SERVICE_PORT=8002
   ```
---

## 🏗️ Defining Models

### **Approach**: Use common layer for shared models

#### **1. Create Database Models (SQLAlchemy/Raw SQL)**

**Location**: `common/models/db_models.py`

```python
# Example structure - DO NOT IMPLEMENT YET
from sqlalchemy import Column, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
import uuid

Base = declarative_base()

class Source(Base):
    __tablename__ = "sources"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    url = Column(Text, unique=True, nullable=False)
    category = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

class Article(Base):
    __tablename__ = "articles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url = Column(Text, unique=True, nullable=False)
    title = Column(Text)
    content = Column(Text)
    source_id = Column(UUID(as_uuid=True), ForeignKey('sources.id'))
    published_at = Column(DateTime)
    analysis_status = Column(String(50), default='pending')
    created_at = Column(DateTime, server_default=func.now())
```




#### **2. Create API Models (Pydantic)**

**Location**: `common/models/db_models.py`

```python
# Example structure - DO NOT IMPLEMENT YET
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid

class SourceCreate(BaseModel):
    name: str
    url: str
    category: Optional[str] = None

class SourceResponse(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    category: Optional[str]
    is_active: bool
    created_at: datetime

class ArticleCreate(BaseModel):
    url: str
    title: Optional[str] = None
    source_id: Optional[uuid.UUID] = None

class ArticleResponse(BaseModel):
    id: uuid.UUID
    url: str
    title: Optional[str]
    content: Optional[str]
    source_id: Optional[uuid.UUID]
    analysis_status: str
    created_at: datetime
```



#### **3. Database Schema Migrations**

**Location**: `microservices/db/migrations/`

```sql
-- Example: 001_initial_schema.sql
-- DO NOT IMPLEMENT YET

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    url TEXT UNIQUE NOT NULL,
    category VARCHAR(100),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

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

-- Indexes for performance
CREATE INDEX idx_articles_source_id ON articles(source_id);
CREATE INDEX idx_articles_status ON articles(analysis_status);
CREATE INDEX idx_articles_created_at ON articles(created_at);
```

---

## 🔗 Defining Endpoints

### **Approach**: Add endpoints to existing services, not DB service

#### **1. API Gateway Endpoints (External API)**

**Location**: `microservices/api_gateway/routers/`

The API Gateway now uses a modular router structure:
- `routers/articles.py` - Article-related endpoints
- `routers/sources.py` - RSS source management  
- `routers/database.py` - Database status and health
- `routers/analysis.py` - Content analysis (existing)
- `routers/health.py` - Service health checks

```python
# Example endpoints in routers/articles.py - DO NOT IMPLEMENT YET

from fastapi import APIRouter
router = APIRouter(prefix="/articles", tags=["articles"])

@router.get("/", response_model=List[ArticleResponse])
async def list_articles(
    limit: int = 10,
    offset: int = 0,
    status: Optional[str] = None
):
    """List articles with pagination and filtering"""
    # Implementation goes here
    pass

@router.get("/{article_id}", response_model=ArticleResponse)
async def get_article(article_id: uuid.UUID):
    """Get specific article by ID"""
    # Implementation goes here
    pass

@router.get("/search")
async def search_articles(
    query: str,
    limit: int = 10
):
    """Search articles by content/title"""
    # Implementation goes here
    pass
```

```python
# Example endpoints in routers/sources.py - DO NOT IMPLEMENT YET

from fastapi import APIRouter
router = APIRouter(prefix="/sources", tags=["sources"])

@router.get("/", response_model=List[SourceResponse])
async def list_sources():
    """List RSS sources"""
    # Implementation goes here
    pass

@router.post("/", response_model=SourceResponse)
async def create_source(source: SourceCreate):
    """Create new RSS source"""
    # Implementation goes here
    pass
```

#### **2. Database Utilities for Services**

**Location**: `common/db_client/connection.py`

```python
# Example connection utilities - DO NOT IMPLEMENT YET
import asyncpg
import os
from typing import Optional

class DatabaseConnection:
    _pool: Optional[asyncpg.Pool] = None
    
    @classmethod
    async def get_pool(cls) -> asyncpg.Pool:
        if cls._pool is None:
            cls._pool = await asyncpg.create_pool(
                host=os.getenv("POSTGRES_HOST", "postgres"),
                port=int(os.getenv("POSTGRES_PORT", 5432)),
                database=os.getenv("POSTGRES_DB", "sentinel_db"),
                user=os.getenv("POSTGRES_USER", "sentinel_user"),
                password=os.getenv("POSTGRES_PASSWORD"),
                min_size=2,
                max_size=10
            )
        return cls._pool

async def execute_query(query: str, *args):
    pool = await DatabaseConnection.get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)

async def fetch_query(query: str, *args):
    pool = await DatabaseConnection.get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)
```

#### **3. Repository Pattern (Optional)**

**Location**: `common/db_client/repositories.py`

```python
# Example repository pattern - DO NOT IMPLEMENT YET
from typing import List, Optional
import uuid

class ArticleRepository:
    @staticmethod
    async def create_article(article_data: dict) -> dict:
        query = """
        INSERT INTO articles (url, title, source_id, published_at)
        VALUES ($1, $2, $3, $4)
        RETURNING id, url, title, source_id, analysis_status, created_at
        """
        result = await fetch_query(
            query, 
            article_data['url'], 
            article_data.get('title'),
            article_data.get('source_id'),
            article_data.get('published_at')
        )
        return dict(result[0]) if result else None
    
    @staticmethod
    async def get_article_by_id(article_id: uuid.UUID) -> Optional[dict]:
        query = "SELECT * FROM articles WHERE id = $1"
        result = await fetch_query(query, article_id)
        return dict(result[0]) if result else None
    
    @staticmethod
    async def list_articles(limit: int = 10, offset: int = 0) -> List[dict]:
        query = """
        SELECT * FROM articles 
        ORDER BY created_at DESC 
        LIMIT $1 OFFSET $2
        """
        result = await fetch_query(query, limit, offset)
        return [dict(row) for row in result]

class SourceRepository:
    @staticmethod
    async def create_source(source_data: dict) -> dict:
        query = """
        INSERT INTO sources (name, url, category)
        VALUES ($1, $2, $3)
        RETURNING id, name, url, category, is_active, created_at
        """
        result = await fetch_query(
            query,
            source_data['name'],
            source_data['url'],
            source_data.get('category')
        )
        return dict(result[0]) if result else None
```

---

## ⚙️ Core Database Services

### **Essential Services to Implement:**

#### **1. Database Health Monitoring**
```python
# Add to routers/database.py - DO NOT IMPLEMENT YET
@router.get("/health")
async def database_health():
    try:
        # Test connection
        await execute_query("SELECT 1")
        
        # Get statistics
        stats = await fetch_query("""
            SELECT 
                (SELECT COUNT(*) FROM articles) as total_articles,
                (SELECT COUNT(*) FROM sources) as total_sources,
                (SELECT COUNT(*) FROM articles WHERE analysis_status = 'pending') as pending_articles
        """)
        
        return {
            "status": "healthy",
            "statistics": dict(stats[0]) if stats else {}
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

#### **2. Database Migrations Service**
```bash
# Migration management - DO NOT IMPLEMENT YET
# Add to scripts/database/migrate.sh

#!/bin/bash
# Apply database migrations

echo "Applying database migrations..."

# Run migration files in order
for migration in microservices/db/migrations/*.sql; do
    echo "Applying: $migration"
    docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -f "/docker-entrypoint-initdb.d/$(basename $migration)"
done

echo "Migrations completed"
```

#### **3. Data Backup Service**
```bash
# Backup script - DO NOT IMPLEMENT YET
# Add to scripts/database/backup.sh

#!/bin/bash
# Backup database

BACKUP_DIR="./backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="sentinel_backup_$TIMESTAMP.sql"

mkdir -p $BACKUP_DIR

echo "Creating backup: $BACKUP_FILE"
docker compose exec postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB > "$BACKUP_DIR/$BACKUP_FILE"

echo "Backup completed: $BACKUP_DIR/$BACKUP_FILE"
```

#### **4. Database Seeding**
```python
# Seed data script - DO NOT IMPLEMENT YET
# Add to scripts/database/seed.py

async def seed_database():
    """Seed database with initial data"""
    
    # Seed RSS sources
    sources = [
        {"name": "BBC News", "url": "http://feeds.bbci.co.uk/news/rss.xml", "category": "news"},
        {"name": "Reuters", "url": "http://feeds.reuters.com/reuters/topNews", "category": "news"},
    ]
    
    for source_data in sources:
        await SourceRepository.create_source(source_data)
    
    print("Database seeded successfully")
```

---

## 🔍 pgvector Integration

### **pgvector Requires Different Approach:**

#### **1. Vector-Specific Tables**
```sql
-- DO NOT IMPLEMENT YET
-- Vector embeddings table
CREATE TABLE article_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID REFERENCES articles(id) ON DELETE CASCADE,
    embedding vector(1536),  -- OpenAI ada-002 dimensions
    model_name VARCHAR(100) NOT NULL,
    embedding_type VARCHAR(50) DEFAULT 'content', -- title, content, summary
    created_at TIMESTAMP DEFAULT NOW()
);

-- Vector indexes for performance
CREATE INDEX ON article_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

#### **2. Vector Operations**
```python
# DO NOT IMPLEMENT YET
# Add to common/db_client/vector_operations.py

async def store_embedding(article_id: uuid.UUID, embedding: List[float], model_name: str):
    """Store article embedding"""
    query = """
    INSERT INTO article_embeddings (article_id, embedding, model_name)
    VALUES ($1, $2, $3)
    """
    await execute_query(query, article_id, embedding, model_name)

async def find_similar_articles(query_embedding: List[float], limit: int = 10):
    """Find similar articles using cosine similarity"""
    query = """
    SELECT a.id, a.title, a.url, 
           1 - (ae.embedding <=> $1) as similarity
    FROM article_embeddings ae
    JOIN articles a ON ae.article_id = a.id
    ORDER BY ae.embedding <=> $1
    LIMIT $2
    """
    return await fetch_query(query, query_embedding, limit)

async def semantic_search(query_text: str, limit: int = 10):
    """Perform semantic search (requires embedding generation)"""
    # 1. Generate embedding for query_text (using OpenAI/other service)
    # 2. Search using find_similar_articles
    pass
```

#### **3. Vector Endpoints**
```python
# DO NOT IMPLEMENT YET
# Add to routers/articles.py

@router.post("/{article_id}/embedding")
async def generate_embedding(article_id: uuid.UUID):
    """Generate and store embedding for article"""
    # 1. Get article content
    # 2. Generate embedding (call NLP service)
    # 3. Store in database
    pass

@router.get("/similar/{article_id}")
async def find_similar(article_id: uuid.UUID, limit: int = 10):
    """Find articles similar to given article"""
    # 1. Get article embedding
    # 2. Find similar articles
    pass

@router.post("/search/semantic")
async def semantic_search(query: str, limit: int = 10):
    """Semantic search across articles"""
    # 1. Generate embedding for query
    # 2. Find similar articles
    pass
```

#### **4. Integration with NLP Service**
```python
# DO NOT IMPLEMENT YET
# Modify NLP service to store embeddings after analysis

# In NLP service:
async def analyze_and_embed(article_data: dict):
    # 1. Perform NLP analysis
    analysis_result = await perform_nlp_analysis(article_data)
    
    # 2. Generate embedding
    embedding = await generate_embedding(article_data['content'])
    
    # 3. Store both in database
    await store_analysis_result(article_data['id'], analysis_result)
    await store_embedding(article_data['id'], embedding, "text-embedding-ada-002")
    
    return analysis_result
```

---

## ✅ Best Practices

### **Development Workflow:**

1. **Start Small**: Implement basic CRUD operations first
2. **Test Incrementally**: Add one model/endpoint at a time
3. **Use Transactions**: Wrap related operations in database transactions
4. **Connection Pooling**: Always use connection pools for performance
5. **Error Handling**: Implement proper error handling and logging
6. **Validation**: Validate data at API and database levels

### **Performance Considerations:**

1. **Indexing**: Add indexes for frequently queried columns
2. **Pagination**: Always paginate large result sets
3. **Caching**: Cache frequently accessed data in Redis
4. **Bulk Operations**: Use bulk inserts for large datasets
5. **Vector Indexes**: Use appropriate vector index types for pgvector

### **Security:**

1. **Input Validation**: Sanitize all user inputs
2. **SQL Injection**: Use parameterized queries
3. **Connection Security**: Use SSL for database connections
4. **Access Control**: Implement proper user roles and permissions

### **Monitoring:**

1. **Query Performance**: Monitor slow queries
2. **Connection Usage**: Track connection pool utilization
3. **Storage Growth**: Monitor database size and growth
4. **Vector Operations**: Monitor embedding generation and search performance

---

## 🚀 Implementation Order

### **Phase 1**: Basic CRUD (Week 1)
1. Create database models
2. Implement basic connection utilities
3. Add article and source endpoints
4. Test basic operations

### **Phase 2**: Integration (Week 2)
1. Integrate with existing services (Ingestor, NLP)
2. Add data validation and error handling
3. Implement search functionality

### **Phase 3**: Vector Operations (Week 3)
1. Add pgvector tables and indexes
2. Implement embedding storage and retrieval
3. Add semantic search endpoints
4. Integrate with NLP service for automatic embedding

### **Phase 4**: Optimization (Week 4)
1. Performance tuning and indexing
2. Connection pool optimization
3. Caching strategy implementation
4. Monitoring and alerting

**Remember: Always ask before implementing any of these features!**
