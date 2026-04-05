import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session

from microservices.retrieval_layer.config import (
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    POSTGRES_HOST,
    POSTGRES_PORT,
    POSTGRES_DB,
)
from microservices.retrieval_layer.db.models import Base

logger = logging.getLogger(__name__)

DATABASE_URL = (
    f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def ensure_schema_compatibility() -> None:
    """Idempotently backfill legacy retrieval schema changes on existing DB volumes."""
    Base.metadata.create_all(engine)

    article_column_statements = {
        "title": "ALTER TABLE article ADD COLUMN IF NOT EXISTS title VARCHAR(1024)",
        "publishedat": "ALTER TABLE article ADD COLUMN IF NOT EXISTS publishedat TIMESTAMP WITH TIME ZONE",
        "sentiment_id": "ALTER TABLE article ADD COLUMN IF NOT EXISTS sentiment_id INTEGER",
        "outlet_id": "ALTER TABLE article ADD COLUMN IF NOT EXISTS outlet_id INTEGER",
        "author_id": "ALTER TABLE article ADD COLUMN IF NOT EXISTS author_id INTEGER",
    }

    with engine.begin() as connection:
        inspector = inspect(connection)
        if "article" not in inspector.get_table_names():
            logger.info("Retrieval DB schema created from metadata.")
            return

        existing_columns = {column["name"] for column in inspector.get_columns("article")}
        for column_name, statement in article_column_statements.items():
            if column_name not in existing_columns:
                connection.execute(text(statement))
                logger.info("Retrieval DB migration: added article.%s", column_name)

        connection.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'fk_article_outlet'
                    ) THEN
                        ALTER TABLE article
                        ADD CONSTRAINT fk_article_outlet
                        FOREIGN KEY (outlet_id) REFERENCES news_outlet(id)
                        ON DELETE SET NULL;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'fk_article_sentiment'
                    ) THEN
                        ALTER TABLE article
                        ADD CONSTRAINT fk_article_sentiment
                        FOREIGN KEY (sentiment_id) REFERENCES sentiment_analysis(id)
                        ON DELETE SET NULL;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'fk_article_author'
                    ) THEN
                        ALTER TABLE article
                        ADD CONSTRAINT fk_article_author
                        FOREIGN KEY (author_id) REFERENCES author(id)
                        ON DELETE SET NULL;
                    END IF;
                END
                $$;
                """
            )
        )


def get_db_session() -> Session:
    return SessionLocal()

@contextmanager
def get_db_transaction() -> Session:
    """Get a session with automatic transaction management."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
