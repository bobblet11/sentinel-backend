#!/bin/bash
# ============================================================================
# Database Migration Script
# Description: Applies SQL migrations in order
# Usage: ./scripts/database/migrate.sh
# ============================================================================

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Sentinel Database Migration${NC}"
echo -e "${GREEN}========================================${NC}"

# Determine if we need sudo for docker
DOCKER_CMD="docker"
if ! docker ps >/dev/null 2>&1; then
    if sudo docker ps >/dev/null 2>&1; then
        DOCKER_CMD="sudo docker"
        echo -e "${YELLOW}Using sudo for Docker commands${NC}"
    else
        echo -e "${RED}Error: Cannot access Docker${NC}"
        exit 1
    fi
fi

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Set defaults if not in .env
POSTGRES_USER=${POSTGRES_USER:-sentinel_user}
POSTGRES_DB=${POSTGRES_DB:-sentinel_db}
MIGRATION_DIR="./microservices/db/migrations"

# Check if postgres container is running
if ! $DOCKER_CMD compose ps postgres | grep -q "Up"; then
    echo -e "${RED}Error: PostgreSQL container is not running${NC}"
    echo "Start it with: $DOCKER_CMD compose up postgres -d"
    exit 1
fi

# Check if migrations directory exists
if [ ! -d "$MIGRATION_DIR" ]; then
    echo -e "${RED}Error: Migrations directory not found: $MIGRATION_DIR${NC}"
    exit 1
fi

# Count migration files
MIGRATION_COUNT=$(find "$MIGRATION_DIR" -name "*.sql" | wc -l)
if [ "$MIGRATION_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}No migration files found in $MIGRATION_DIR${NC}"
    exit 0
fi

echo -e "${GREEN}Found $MIGRATION_COUNT migration(s)${NC}"
echo ""

# Apply migrations in order
for migration_file in $(find "$MIGRATION_DIR" -name "*.sql" | sort); do
    migration_name=$(basename "$migration_file")
    echo -e "${YELLOW}Applying: $migration_name${NC}"
    
    # Copy migration to container and execute
    $DOCKER_CMD compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$migration_file"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Successfully applied: $migration_name${NC}"
    else
        echo -e "${RED}✗ Failed to apply: $migration_name${NC}"
        exit 1
    fi
    echo ""
done

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}All migrations applied successfully!${NC}"
echo -e "${GREEN}========================================${NC}"

# Show table count
echo ""
echo -e "${YELLOW}Database Summary:${NC}"
$DOCKER_CMD compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT 
    schemaname,
    COUNT(*) as table_count
FROM pg_tables 
WHERE schemaname = 'public'
GROUP BY schemaname;
"

echo ""
echo -e "${YELLOW}Tables Created:${NC}"
$DOCKER_CMD compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT tablename 
FROM pg_tables 
WHERE schemaname = 'public' 
ORDER BY tablename;
"
