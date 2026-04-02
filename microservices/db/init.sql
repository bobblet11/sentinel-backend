-- ============================================================================
-- Sentinel Database Initialization
-- Description: Enables required PostgreSQL extensions
-- Note: Actual schema is in migrations/
-- ============================================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pgvector for embeddings (future use)
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable trigram similarity for fuzzy text search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================================
-- Create sentinel_user role with proper credentials and permissions
-- ============================================================================
DO $$ 
BEGIN
  -- Create role if it doesn't exist, or alter password if it does
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'sentinel_user') THEN
    CREATE ROLE sentinel_user WITH LOGIN PASSWORD 'Sentinel12345' SUPERUSER CREATEDB CREATEROLE;
  ELSE
    ALTER ROLE sentinel_user WITH PASSWORD 'Sentinel12345';
  END IF;
END 
$$;

-- Grant privileges on the currently connected database.
-- This avoids hardcoding a DB name that may differ by environment.
DO $$
DECLARE
  current_db text := current_database();
BEGIN
  EXECUTE format('GRANT ALL PRIVILEGES ON DATABASE %I TO %I', current_db, current_user);

  IF EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'sentinel_user') THEN
    EXECUTE format('GRANT ALL PRIVILEGES ON DATABASE %I TO sentinel_user', current_db);
  END IF;
END
$$;

BEGIN;


CREATE TABLE IF NOT EXISTS article (
	id SERIAL PRIMARY KEY,
	url VARCHAR(250) NOT NULL,
	html TEXT,
	text TEXT,
	UNIQUE (url)
);
COMMENT ON TABLE article IS 'Records each submitted article, either by user or by ingestor';


CREATE TABLE IF NOT EXISTS news_outlet (
	id SERIAL PRIMARY KEY,
	name VARCHAR(50) NOT NULL,
	UNIQUE (name)
);
COMMENT ON TABLE news_outlet IS 'Records each news outlet. everytime a new outlet is submitted through an article, new outlet is added here';

CREATE TABLE IF NOT EXISTS job (
	id SERIAL PRIMARY KEY,
	uid CHAR(36) NOT NULL UNIQUE,
	article_id INTEGER NOT NULL,
	status VARCHAR(50) NOT NULL DEFAULT 'pending',
	type VARCHAR(20) NOT NULL DEFAULT 'background',
    	created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

	CONSTRAINT fk_article
		FOREIGN KEY(article_id) 
		REFERENCES article(id)
		ON DELETE CASCADE
);

COMMENT ON TABLE job IS 'Stores the primary information for each processing job.';
COMMENT ON COLUMN job.status IS 'The current status of the job, e.g., pending, completed, failed.';

CREATE TABLE IF NOT EXISTS job_timestamp (
	id SERIAL PRIMARY KEY,
	job_id INTEGER NOT NULL,
	stage_name VARCHAR(50) NOT NULL,
    	timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

	CONSTRAINT fk_job
		FOREIGN KEY(job_id) 
		REFERENCES job(id)
		ON DELETE CASCADE,
	UNIQUE (job_id, stage_name)
);	

COMMENT ON TABLE job_timestamp IS 'Records timestamps for various pipeline stages for a given job.';
COMMENT ON COLUMN job_timestamp.stage_name IS 'The name of the pipeline stage, e.g., ''ingested'', ''scraped''.';

CREATE INDEX IF NOT EXISTS idx_job_timestamp_job_id ON job_timestamp(job_id);

CREATE TABLE IF NOT EXISTS author (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sentiment_analysis (
    id SERIAL PRIMARY KEY,
    bias_category VARCHAR(50),
    bias_score FLOAT,
    bias_analysis_confidence FLOAT,
    sentiment_category VARCHAR(50),
    sentiment_analysis_confidence FLOAT
);

ALTER TABLE article
ADD COLUMN IF NOT EXISTS title VARCHAR(1024),
ADD COLUMN IF NOT EXISTS publishedat TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS sentiment_id INTEGER,
ADD COLUMN IF NOT EXISTS outlet_id INTEGER;

ALTER TABLE article ADD COLUMN IF NOT EXISTS author_id INTEGER;
ALTER TABLE article ADD CONSTRAINT fk_article_author 
FOREIGN KEY (author_id) REFERENCES author(id) ON DELETE SET NULL;

ALTER TABLE article
ADD CONSTRAINT fk_article_outlet
FOREIGN KEY (outlet_id) REFERENCES news_outlet(id)
ON DELETE SET NULL;

ALTER TABLE article
ADD CONSTRAINT fk_article_sentiment
FOREIGN KEY (sentiment_id) REFERENCES sentiment_analysis(id)
ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS entity (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entity_name ON entity(name);

CREATE TABLE IF NOT EXISTS claim (
    id SERIAL PRIMARY KEY,
    original_sentence TEXT NOT NULL,
    decontextualised_claim TEXT,
    decontextualised_embedding VECTOR(768),
    centrality_score FLOAT,
    article_id INTEGER NOT NULL,

    CONSTRAINT fk_claim_article
        FOREIGN KEY(article_id)
        REFERENCES article(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_claim_embedding_hnsw
ON claim
USING hnsw (decontextualised_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE TABLE IF NOT EXISTS claim_to_entity (
    claim_id INTEGER NOT NULL,
    entity_id INTEGER NOT NULL,

    PRIMARY KEY (claim_id, entity_id),

    CONSTRAINT fk_cte_claim
        FOREIGN KEY (claim_id)
        REFERENCES claim(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_cte_entity
        FOREIGN KEY (entity_id)
        REFERENCES entity(id)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_claim_to_entity_entity_id ON claim_to_entity (entity_id);
CREATE INDEX IF NOT EXISTS idx_claim_to_entity_claim_id ON claim_to_entity (claim_id);


COMMIT;
