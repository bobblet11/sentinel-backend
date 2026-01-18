#!/bin/bash
# ============================================================================
# Insert Custom Data into Database
# Usage: ./scripts/database/insert.sh <table> '<column1>' 'value1' '<column2>' 'value2' ...
#
# Examples:
#   ./scripts/database/insert.sh sources 'name' 'CNN' 'domain' 'cnn.com' 'credibility_score' '82'
#   ./scripts/database/insert.sh topics 'name' 'Sports'
# ============================================================================

COMPOSE_FILE="/workspaces/Sentinel/docker/compose/docker-compose.yml"
TABLE=$1
shift

if [ -z "$TABLE" ]; then
    echo "Usage: $0 <table> '<column>' 'value' [...]"
    echo ""
    echo "Tables available:"
    echo "  - sources (name, domain, default_bias, credibility_score)"
    echo "  - articles (url, title, author, published_at, source_id)"
    echo "  - topics (name, description)"
    echo "  - claims (result_id, claim_text, verdict, confidence)"
    echo "  - evidence (claim_id, source, url, excerpt)"
    exit 1
fi

# Build the INSERT statement
COLUMNS=""
VALUES=""
count=1

while [ $# -gt 0 ]; do
    COLUMN=$1
    VALUE=$2
    shift 2
    
    if [ -n "$COLUMNS" ]; then
        COLUMNS="$COLUMNS, "
        VALUES="$VALUES, "
    fi
    
    COLUMNS="${COLUMNS}${COLUMN}"
    VALUES="${VALUES}'${VALUE}'"
done

SQL="INSERT INTO $TABLE ($COLUMNS) VALUES ($VALUES) RETURNING *;"

echo "Executing: $SQL"
echo "$SQL" | sudo docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U sentinel_user -d sentinel_db
