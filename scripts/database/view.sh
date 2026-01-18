#!/bin/bash
# ============================================================================
# View Database Tables and Data
# Usage: 
#   ./scripts/database/view.sh              # List all tables
#   ./scripts/database/view.sh articles     # View articles table
#   ./scripts/database/view.sh sources      # View sources table
# ============================================================================

COMPOSE_FILE="/workspaces/Sentinel/docker/compose/docker-compose.yml"
TABLE=${1:-}

if [ -z "$TABLE" ]; then
    # List all tables
    echo "📊 Database Tables:"
    echo "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;" | \
    sudo docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U sentinel_user -d sentinel_db
    exit 0
fi

# Show table structure
echo "📋 Table: $TABLE (Structure)"
echo "\d $TABLE" | \
sudo docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U sentinel_user -d sentinel_db

echo ""
echo "📊 Table: $TABLE (Data - First 10 rows)"
echo "SELECT * FROM $TABLE LIMIT 10;" | \
sudo docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U sentinel_user -d sentinel_db

echo ""
echo "📈 Row Count: $TABLE"
echo "SELECT COUNT(*) as total_rows FROM $TABLE;" | \
sudo docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U sentinel_user -d sentinel_db
