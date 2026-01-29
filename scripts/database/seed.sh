#!/bin/bash
# ============================================================================
# Insert Sample Data into Database
# Usage: ./scripts/database/seed.sh
# ============================================================================

COMPOSE_FILE="/workspaces/Sentinel/docker/compose/docker-compose.yml"

echo "🌱 Seeding database with sample data..."

# Insert sample sources
echo "📰 Adding news sources..."
cat <<EOF | sudo docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U sentinel_user -d sentinel_db
INSERT INTO sources (source_id, name, domain, default_bias, credibility_score, is_active)
VALUES 
  (gen_random_uuid(), 'BBC News', 'bbc.com', 'center', 85, true),
  (gen_random_uuid(), 'Reuters', 'reuters.com', 'center', 90, true),
  (gen_random_uuid(), 'NPR', 'npr.org', 'center-left', 80, true),
  (gen_random_uuid(), 'Fox News', 'foxnews.com', 'center-right', 75, true),
  (gen_random_uuid(), 'The Guardian', 'theguardian.com', 'left', 78, true)
ON CONFLICT DO NOTHING;
EOF

# Insert sample articles
echo "📄 Adding sample articles..."
cat <<EOF | sudo docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U sentinel_user -d sentinel_db
INSERT INTO articles (article_id, url, title, author, published_at, source_id)
SELECT
  gen_random_uuid(),
  'https://example.com/article-' || (ROW_NUMBER() OVER()),
  'Sample Article ' || (ROW_NUMBER() OVER ()),
  'Staff Writer',
  NOW() - INTERVAL '1 day' * (ROW_NUMBER() OVER ()),
  (SELECT source_id FROM sources ORDER BY RANDOM() LIMIT 1)
FROM (SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3) as t
LIMIT 5
ON CONFLICT DO NOTHING;
EOF

# Insert sample topics
echo "🏷️  Adding sample topics..."
cat <<EOF | sudo docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U sentinel_user -d sentinel_db
INSERT INTO topics (topic_id, name, description)
VALUES
  (gen_random_uuid(), 'Politics', 'Political news and analysis'),
  (gen_random_uuid(), 'Technology', 'Technology and innovation'),
  (gen_random_uuid(), 'Health', 'Health and medical news'),
  (gen_random_uuid(), 'Science', 'Science and research'),
  (gen_random_uuid(), 'Business', 'Business and economics')
ON CONFLICT DO NOTHING;
EOF

echo "✅ Sample data seeded successfully!"
echo ""
echo "View data with:"
echo "  ./scripts/database/view.sh articles"
echo "  ./scripts/database/view.sh sources"
echo "  ./scripts/database/view.sh topics"
