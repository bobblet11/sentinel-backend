-- ============================================================================
-- Sentinel Database Schema - Initial Migration
-- Version: 001
-- Created: 2026-01-18
-- Description: Creates core tables for article analysis, claims, and evidence
-- ============================================================================

-- Create custom ENUM types
CREATE TYPE job_status AS ENUM ('pending', 'processing', 'completed', 'failed');
CREATE TYPE bias_category AS ENUM ('left', 'center-left', 'center', 'center-right', 'right', 'unknown');
CREATE TYPE claim_verdict AS ENUM ('true', 'mostly_true', 'mixed', 'mostly_false', 'false', 'unverifiable');
CREATE TYPE evidence_category AS ENUM ('language', 'source_selection', 'framing', 'omission', 'factual');

-- ============================================================================
-- Core Tables
-- ============================================================================

-- Source (News outlets)
CREATE TABLE sources (
    source_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    domain TEXT UNIQUE NOT NULL,
    default_bias bias_category DEFAULT 'unknown',
    credibility_score INT CHECK (credibility_score >= 0 AND credibility_score <= 100),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Articles
CREATE TABLE articles (
    article_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    content TEXT,
    author TEXT,
    published_at TIMESTAMP,
    article_html TEXT,
    source_id UUID REFERENCES sources(source_id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Analysis Jobs (tracks processing status)
CREATE TABLE analysis_jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,
    status job_status DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    is_cached_result BOOLEAN DEFAULT false,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Article Analysis Results
CREATE TABLE article_analysis_results (
    result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES analysis_jobs(job_id) ON DELETE CASCADE,
    trust_score INT CHECK (trust_score >= 0 AND trust_score <= 100),
    model_version TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(article_id, job_id)
);

-- ============================================================================
-- Analysis Components
-- ============================================================================

-- Political Bias Indicators
CREATE TABLE political_indicators (
    political_indicator_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    result_id UUID NOT NULL REFERENCES article_analysis_results(result_id) ON DELETE CASCADE,
    overall_bias bias_category DEFAULT 'unknown',
    bias_score INT CHECK (bias_score >= -100 AND bias_score <= 100),
    confidence INT CHECK (confidence >= 0 AND confidence <= 100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Evidence for Political Indicators
CREATE TABLE political_indicator_evidence (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    political_indicator_id UUID NOT NULL REFERENCES political_indicators(political_indicator_id) ON DELETE CASCADE,
    category evidence_category NOT NULL,
    sentence TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Claims Extracted from Articles
CREATE TABLE claims (
    claim_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    result_id UUID NOT NULL REFERENCES article_analysis_results(result_id) ON DELETE CASCADE,
    claim_text TEXT NOT NULL,
    verdict claim_verdict,
    confidence INT CHECK (confidence >= 0 AND confidence <= 100),
    embedding_id UUID, -- Reference to vector embedding (for future pgvector integration)
    created_at TIMESTAMP DEFAULT NOW()
);

-- Evidence Supporting Claims
CREATE TABLE evidence (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
    source TEXT,
    url TEXT,
    excerpt TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Related Coverage from Other Sources
CREATE TABLE related_coverage (
    coverage_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    result_id UUID NOT NULL REFERENCES article_analysis_results(result_id) ON DELETE CASCADE,
    related_article_id UUID REFERENCES articles(article_id) ON DELETE SET NULL,
    bias bias_category,
    excerpt TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================================
-- Topic Management (Many-to-Many)
-- ============================================================================

-- Topics
CREATE TABLE topics (
    topic_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Article-Topic Junction Table
CREATE TABLE article_topics (
    article_id UUID NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,
    topic_id UUID NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (article_id, topic_id)
);

-- ============================================================================
-- Indexes for Performance
-- ============================================================================

-- Articles
CREATE INDEX idx_articles_source_id ON articles(source_id);
CREATE INDEX idx_articles_published_at ON articles(published_at DESC);
CREATE INDEX idx_articles_created_at ON articles(created_at DESC);
CREATE INDEX idx_articles_url_hash ON articles USING hash(url);

-- Analysis Jobs
CREATE INDEX idx_analysis_jobs_article_id ON analysis_jobs(article_id);
CREATE INDEX idx_analysis_jobs_status ON analysis_jobs(status);
CREATE INDEX idx_analysis_jobs_created_at ON analysis_jobs(created_at DESC);

-- Article Analysis Results
CREATE INDEX idx_results_article_id ON article_analysis_results(article_id);
CREATE INDEX idx_results_job_id ON article_analysis_results(job_id);
CREATE INDEX idx_results_trust_score ON article_analysis_results(trust_score);

-- Political Indicators
CREATE INDEX idx_political_indicators_result_id ON political_indicators(result_id);

-- Political Indicator Evidence
CREATE INDEX idx_pol_evidence_indicator_id ON political_indicator_evidence(political_indicator_id);

-- Claims
CREATE INDEX idx_claims_result_id ON claims(result_id);
CREATE INDEX idx_claims_verdict ON claims(verdict);

-- Evidence
CREATE INDEX idx_evidence_claim_id ON evidence(claim_id);

-- Related Coverage
CREATE INDEX idx_related_coverage_result_id ON related_coverage(result_id);
CREATE INDEX idx_related_coverage_article_id ON related_coverage(related_article_id);

-- Article Topics
CREATE INDEX idx_article_topics_topic_id ON article_topics(topic_id);

-- ============================================================================
-- Full-Text Search Indexes
-- ============================================================================

CREATE INDEX idx_articles_title_fulltext ON articles USING gin(to_tsvector('english', title));
CREATE INDEX idx_articles_content_fulltext ON articles USING gin(to_tsvector('english', content));
CREATE INDEX idx_claims_text_fulltext ON claims USING gin(to_tsvector('english', claim_text));

-- ============================================================================
-- Migration Complete
-- ============================================================================
