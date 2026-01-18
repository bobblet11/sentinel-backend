#!/bin/bash
# ============================================================================
# PostgreSQL Interactive Shell
# Usage: ./scripts/database/psql.sh
# ============================================================================

cd /workspaces/Sentinel/docker/compose
sudo docker compose exec postgres psql -U sentinel_user -d sentinel_db
