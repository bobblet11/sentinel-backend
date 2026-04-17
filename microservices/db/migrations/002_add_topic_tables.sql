-- Migration 002: Add topic classification tables
-- Purely additive — no changes to existing tables.
-- Safe to run on a live database.
--
-- Rollback:
--   DROP TABLE IF EXISTS article_topic;
--   DROP TABLE IF EXISTS topic;

BEGIN;

CREATE TABLE IF NOT EXISTS topic (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,

    CONSTRAINT uq_topic_name UNIQUE (name)
);

-- Seed the 9 predefined topic labels.
INSERT INTO topic (name) VALUES
    ('Politics'),
    ('World'),
    ('Technology'),
    ('Health'),
    ('Science'),
    ('Business'),
    ('Entertainment'),
    ('Sports'),
    ('General')
ON CONFLICT (name) DO NOTHING;

CREATE TABLE IF NOT EXISTS article_topic (
    id         SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL,
    topic_id   INTEGER NOT NULL,
    confidence FLOAT   NOT NULL,

    CONSTRAINT uq_article_topic_article UNIQUE (article_id),

    CONSTRAINT fk_article_topic_article
        FOREIGN KEY (article_id)
        REFERENCES article(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_article_topic_topic
        FOREIGN KEY (topic_id)
        REFERENCES topic(id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_article_topic_article_id ON article_topic (article_id);
CREATE INDEX IF NOT EXISTS idx_article_topic_topic_id   ON article_topic (topic_id);

COMMIT;
