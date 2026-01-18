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

