# Database Migrations

This directory contains versioned SQL migrations for the Sentinel database schema.

## Migration Naming Convention

Format: `XXX_description.sql`
- `XXX`: Sequential number (001, 002, etc.)
- `description`: Brief description using snake_case

Examples:
- `001_initial_schema.sql`
- `002_add_embeddings.sql`
- `003_add_user_feedback.sql`

## Applying Migrations

### Manual Application
```bash
# From project root (use sudo if needed)
sudo docker compose exec -T postgres psql -U $POSTGRES_USER -d $POSTGRES_DB < microservices/db/migrations/001_initial_schema.sql
```

### Using Migration Script (recommended)
```bash
# Auto-detects if sudo is needed
./scripts/database/migrate.sh
```

## Migration Best Practices

1. **Always use `IF NOT EXISTS`** for CREATE statements when safe
2. **Include rollback instructions** in comments
3. **Test migrations** on development database first
4. **Never modify existing migrations** - create new ones instead
5. **Include indexes** in the same migration as table creation
6. **Document breaking changes** clearly

## Current Migrations

- `001_initial_schema.sql` - Core tables for article analysis system
