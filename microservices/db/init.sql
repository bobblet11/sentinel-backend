-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

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



COMMIT;
