-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

BEGIN;

CREATE TABLE IF NOT EXISTS job (
	id SERIAL PRIMARY KEY,
	status VARCHAR(50) NOT NULL DEFAULT 'pending',
	type VARCHAR(20) NOT NULL DEFAULT 'background',
    	created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
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
