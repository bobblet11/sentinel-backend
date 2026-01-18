# Database Operations Guide

## 🚀 Quick Commands

### View Tables and Data

```bash
# List all tables
./scripts/database/view.sh

# View specific table with structure and data
./scripts/database/view.sh sources
./scripts/database/view.sh articles
./scripts/database/view.sh claims
./scripts/database/view.sh topics
```

### Seed Sample Data

```bash
# Insert sample data (news sources, articles, topics)
./scripts/database/seed.sh
```

### Insert Custom Data

```bash
# Add a new news source
./scripts/database/insert.sh sources 'name' 'CNN' 'domain' 'cnn.com' 'credibility_score' '82'

# Add a topic
./scripts/database/insert.sh topics 'name' 'Sports' 'description' 'Sports news and analysis'

# Add evidence
./scripts/database/insert.sh evidence 'source' 'BBC News' 'url' 'https://bbc.com/article' 'excerpt' 'Key finding'
```

### Interactive psql Shell

```bash
# Open PostgreSQL interactive shell
./scripts/database/psql.sh
```

---

## 📊 Common SQL Queries

### View Data

```sql
-- List all sources
SELECT source_id, name, domain, credibility_score FROM sources;

-- List articles with their source
SELECT a.article_id, a.title, a.url, s.name as source
FROM articles a
LEFT JOIN sources s ON a.source_id = s.source_id
LIMIT 10;

-- Count articles per source
SELECT s.name, COUNT(a.article_id) as article_count
FROM articles a
RIGHT JOIN sources s ON a.source_id = s.source_id
GROUP BY s.name
ORDER BY article_count DESC;

-- View topics
SELECT topic_id, name, description FROM topics;
```

### Insert Data

```sql
-- Insert a new source
INSERT INTO sources (source_id, name, domain, default_bias, credibility_score)
VALUES (
  gen_random_uuid(),
  'Al Jazeera',
  'aljazeera.com',
  'center',
  85
);

-- Insert an article
INSERT INTO articles (article_id, url, title, author, source_id, published_at)
VALUES (
  gen_random_uuid(),
  'https://example.com/breaking-news',
  'Breaking News Title',
  'John Doe',
  (SELECT source_id FROM sources WHERE name = 'BBC News' LIMIT 1),
  NOW()
) RETURNING article_id, url, title;

-- Insert multiple articles
INSERT INTO articles (article_id, url, title, author, published_at)
VALUES
  (gen_random_uuid(), 'https://example.com/1', 'Article 1', 'Author A', NOW()),
  (gen_random_uuid(), 'https://example.com/2', 'Article 2', 'Author B', NOW() - INTERVAL '1 day'),
  (gen_random_uuid(), 'https://example.com/3', 'Article 3', 'Author C', NOW() - INTERVAL '2 days');
```

### Update Data

```sql
-- Update article status
UPDATE articles
SET updated_at = NOW()
WHERE article_id = 'your-article-id';

-- Update source credibility
UPDATE sources
SET credibility_score = 88
WHERE name = 'BBC News';

-- Deactivate a source
UPDATE sources
SET is_active = false
WHERE domain = 'example.com';
```

### Delete Data

```sql
-- Delete articles from a specific source (cascades to analysis jobs, claims, etc.)
DELETE FROM articles
WHERE source_id = (SELECT source_id FROM sources WHERE name = 'Example News');

-- Delete a topic and all related article-topic associations
DELETE FROM topics
WHERE name = 'Old Topic';
```

---

## 🔍 Advanced Queries

### Analytics

```sql
-- Article analysis summary
SELECT
  a.analysis_status,
  COUNT(*) as count,
  AVG(EXTRACT(DAY FROM NOW() - a.created_at))::INT as avg_age_days
FROM analysis_jobs a
GROUP BY a.analysis_status;

-- Trust scores by source
SELECT
  s.name,
  COUNT(r.result_id) as analysis_count,
  AVG(r.trust_score) as avg_trust_score,
  MIN(r.trust_score) as min_trust,
  MAX(r.trust_score) as max_trust
FROM article_analysis_results r
JOIN articles a ON r.article_id = a.article_id
JOIN sources s ON a.source_id = s.source_id
GROUP BY s.name
ORDER BY avg_trust_score DESC;

-- Claims by verdict type
SELECT
  verdict,
  COUNT(*) as count,
  AVG(confidence) as avg_confidence
FROM claims
WHERE verdict IS NOT NULL
GROUP BY verdict
ORDER BY count DESC;

-- Political indicators summary
SELECT
  overall_bias,
  COUNT(*) as count,
  AVG(bias_score) as avg_bias_score,
  AVG(confidence) as avg_confidence
FROM political_indicators
GROUP BY overall_bias
ORDER BY count DESC;
```

### Search and Filter

```sql
-- Search articles by title
SELECT article_id, title, published_at FROM articles
WHERE title ILIKE '%keyword%'
ORDER BY published_at DESC;

-- Find articles by topic
SELECT DISTINCT a.article_id, a.title, t.name
FROM articles a
JOIN article_topics at ON a.article_id = at.article_id
JOIN topics t ON at.topic_id = t.topic_id
WHERE t.name = 'Politics'
ORDER BY a.published_at DESC;

-- Articles pending analysis
SELECT a.article_id, a.title, j.job_id, j.status
FROM articles a
LEFT JOIN analysis_jobs j ON a.article_id = j.article_id
WHERE j.job_id IS NULL OR j.status = 'pending'
LIMIT 20;

-- High-bias articles
SELECT DISTINCT a.article_id, a.title, s.name, p.overall_bias, p.bias_score
FROM articles a
JOIN sources s ON a.source_id = s.source_id
JOIN analysis_jobs j ON a.article_id = j.article_id
JOIN article_analysis_results r ON j.article_id = r.article_id
JOIN political_indicators p ON r.result_id = p.result_id
WHERE ABS(p.bias_score) > 50
ORDER BY ABS(p.bias_score) DESC;
```

---

## 🔗 Table Relationships

```
sources (1) ─── (N) articles
                    ├── (N) analysis_jobs
                    ├── (N) article_analysis_results
                    │        ├── (N) claims
                    │        │        ├── (N) evidence
                    │        │        └── (N) article_analysis_results
                    │        └── (N) political_indicators
                    │             └── (N) political_indicator_evidence
                    └── (N) article_topics ─── (N) topics
```

---

## ⚙️ Tips and Best Practices

1. **Always use UUIDs for IDs** - They're auto-generated with `gen_random_uuid()`
2. **Check constraints** - Trust/bias scores are 0-100, bias_score is -100 to 100
3. **Cascade deletes** - Deleting an article cascades to jobs, claims, evidence, etc.
4. **Use transactions** - For complex operations with multiple tables
5. **Full-text search** - Articles indexed for content and title search

### Transaction Example
```sql
BEGIN;

INSERT INTO articles (article_id, url, title) 
VALUES (gen_random_uuid(), 'https://...', 'Title')
RETURNING article_id;

-- Use the returned ID for related inserts
INSERT INTO analysis_jobs (job_id, article_id, status)
VALUES (gen_random_uuid(), <article_id>, 'pending');

COMMIT;
```

---

## 🆘 Troubleshooting

### Reset Everything
```bash
# Drop all data but keep schema
sudo docker compose -f docker/compose/docker-compose.yml exec postgres psql -U sentinel_user -d sentinel_db -c "
TRUNCATE TABLE political_indicator_evidence CASCADE;
TRUNCATE TABLE political_indicators CASCADE;
TRUNCATE TABLE evidence CASCADE;
TRUNCATE TABLE claims CASCADE;
TRUNCATE TABLE related_coverage CASCADE;
TRUNCATE TABLE article_analysis_results CASCADE;
TRUNCATE TABLE analysis_jobs CASCADE;
TRUNCATE TABLE article_topics CASCADE;
TRUNCATE TABLE articles CASCADE;
TRUNCATE TABLE topics CASCADE;
TRUNCATE TABLE sources CASCADE;
"
```

### Backup Database
```bash
sudo docker compose -f docker/compose/docker-compose.yml exec postgres pg_dump -U sentinel_user sentinel_db > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Restore Database
```bash
sudo docker compose -f docker/compose/docker-compose.yml exec -T postgres psql -U sentinel_user -d sentinel_db < backup_20260118_141000.sql
```
