"""
backfill_topics.py — Backfill topic assignments for articles missing from article_topic.

Only processes articles that have no existing row in article_topic (gap-filling).
Safe to run against a live production database — new articles added by the pipeline
during the run will appear in subsequent runs automatically.

Usage:
    python -m scripts.topic_clustering.backfill_topics --env-file configs/.env

Options:
    --env-file     Path to .env with DB credentials (default: configs/local/.env)
    --batch-size   Articles to process per DB batch (default: 200)
    --threshold    Cosine similarity threshold below which articles get "General"
                   (default: 0.15, must match the value used in TopicClassifier)
    --force        Reclassify all articles, even those already in article_topic
                   (useful after changing descriptions or threshold)
    --dry-run      Classify but do not write to DB — logs what would be written
"""

import argparse
import logging
import sys
from typing import List, Optional, Tuple

import numpy as np

from scripts.topic_clustering.poc_cluster import (
    CONFIDENCE_THRESHOLD,
    PREDEFINED_TOPICS,
    TOPIC_DESCRIPTIONS,
    _build_docs,
    _clean_doc,
    get_engine,
    load_embedding_model,
    load_env,
)
from sqlalchemy import text
from sqlalchemy.engine import Engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── SQL ──────────────────────────────────────────────────────────────────────

_SQL_FETCH_UNCOVERED = text(
    """
    SELECT a.id, a.title, top_c.top_claims
    FROM article a
    LEFT JOIN article_topic at ON at.article_id = a.id
    LEFT JOIN LATERAL (
        SELECT STRING_AGG(decontextualised_claim, ' ') AS top_claims
        FROM (
            SELECT decontextualised_claim
            FROM claim
            WHERE article_id = a.id
              AND decontextualised_claim IS NOT NULL
            ORDER BY centrality_score DESC NULLS LAST
            LIMIT 4
        ) sub
    ) top_c ON true
    WHERE a.title IS NOT NULL AND a.title != ''
      AND at.article_id IS NULL
    ORDER BY a.id
    LIMIT :limit OFFSET :offset
    """
)

_SQL_FETCH_ALL = text(
    """
    SELECT a.id, a.title, top_c.top_claims
    FROM article a
    LEFT JOIN LATERAL (
        SELECT STRING_AGG(decontextualised_claim, ' ') AS top_claims
        FROM (
            SELECT decontextualised_claim
            FROM claim
            WHERE article_id = a.id
              AND decontextualised_claim IS NOT NULL
            ORDER BY centrality_score DESC NULLS LAST
            LIMIT 4
        ) sub
    ) top_c ON true
    WHERE a.title IS NOT NULL AND a.title != ''
    ORDER BY a.id
    LIMIT :limit OFFSET :offset
    """
)

_SQL_FETCH_TOPIC_ID = text("SELECT id FROM topic WHERE name = :name")

_SQL_UPSERT_ARTICLE_TOPIC = text(
    """
    INSERT INTO article_topic (article_id, topic_id, confidence)
    VALUES (:article_id, :topic_id, :confidence)
    ON CONFLICT (article_id)
    DO UPDATE SET topic_id   = EXCLUDED.topic_id,
                  confidence = EXCLUDED.confidence
    """
)


# ── Classification helpers ────────────────────────────────────────────────────

def classify_batch(
    rows: list,
    topic_embs: np.ndarray,
    topic_names: List[str],
    model: "SentenceTransformer",  # noqa: F821
    threshold: float,
) -> List[Tuple[int, str, float]]:
    """Classify a batch of article rows.

    Args:
        rows: List of (id, title, top_claims) tuples from the DB.
        topic_embs: Pre-computed L2-normalised topic embedding matrix (n_topics, 768).
        topic_names: Ordered list of topic name strings matching topic_embs rows.
        model: Pre-loaded SentenceTransformer.
        threshold: Cosine similarity threshold for "General" fallback.

    Returns:
        List of (article_id, topic_label, confidence) tuples.
    """
    import pandas as pd  # noqa: PLC0415

    df = pd.DataFrame(rows, columns=["id", "title", "top_claims"])
    raw_docs = _build_docs(df)
    docs = [_clean_doc(d) for d in raw_docs]

    # Encode non-empty docs only (avoids embedding zero-length strings)
    non_empty_indices = [i for i, d in enumerate(docs) if d]
    results: List[Tuple[int, str, float]] = []

    if non_empty_indices:
        texts_to_encode = [docs[i] for i in non_empty_indices]
        doc_embs = model.encode(
            texts_to_encode, normalize_embeddings=True, show_progress_bar=False, batch_size=64
        )
        sims = doc_embs @ topic_embs.T

    encoded_idx = 0
    for i, row in enumerate(rows):
        article_id = int(row[0])
        if not docs[i]:
            results.append((article_id, "General", 0.0))
            continue

        sim_row = sims[encoded_idx]
        encoded_idx += 1
        best_idx = int(np.argmax(sim_row))
        best_score = float(sim_row[best_idx])
        label = topic_names[best_idx] if best_score >= threshold else "General"
        results.append((article_id, label, round(best_score, 6)))

    return results


# ── Main ─────────────────────────────────────────────────────────────────────

def run_backfill(
    engine: Engine,
    model: "SentenceTransformer",  # noqa: F821
    threshold: float,
    batch_size: int,
    force: bool,
    dry_run: bool,
) -> int:
    """Run the backfill loop.

    Args:
        engine: SQLAlchemy engine connected to the Sentinel DB.
        model: Pre-loaded SentenceTransformer.
        threshold: Cosine similarity threshold for "General" fallback.
        batch_size: Number of articles to fetch and classify per iteration.
        force: If True, reclassify all articles (ignores existing article_topic rows).
        dry_run: If True, log assignments but do not write to DB.

    Returns:
        Total number of articles processed.
    """
    topic_names = [t for t in PREDEFINED_TOPICS if t != "General"]
    description_texts = [TOPIC_DESCRIPTIONS[t] for t in topic_names]

    logger.info("Encoding %d topic descriptions…", len(topic_names))
    topic_embs = model.encode(
        description_texts, normalize_embeddings=True, show_progress_bar=False
    )

    # Cache topic name → DB id mapping
    topic_id_cache: dict = {}
    with engine.connect() as conn:
        for name in PREDEFINED_TOPICS:
            row = conn.execute(_SQL_FETCH_TOPIC_ID, {"name": name}).fetchone()
            if row is None:
                logger.error(
                    "Topic '%s' not found in DB — run 002_add_topic_tables.sql first", name
                )
                sys.exit(1)
            topic_id_cache[name] = int(row[0])

    logger.info("Topic seed verified (%d topics in DB).", len(topic_id_cache))

    fetch_sql = _SQL_FETCH_ALL if force else _SQL_FETCH_UNCOVERED
    offset = 0
    total_processed = 0
    total_skipped = 0

    while True:
        with engine.connect() as conn:
            rows = conn.execute(fetch_sql, {"limit": batch_size, "offset": offset}).fetchall()

        if not rows:
            break

        assignments = classify_batch(rows, topic_embs, topic_names, model, threshold)

        if not dry_run:
            with engine.begin() as conn:
                for article_id, label, confidence in assignments:
                    topic_id = topic_id_cache.get(label, topic_id_cache["General"])
                    conn.execute(
                        _SQL_UPSERT_ARTICLE_TOPIC,
                        {"article_id": article_id, "topic_id": topic_id, "confidence": confidence},
                    )
        else:
            for article_id, label, confidence in assignments:
                logger.info("[DRY RUN] article_id=%d → %s (%.4f)", article_id, label, confidence)

        total_processed += len(assignments)
        offset += batch_size

        if total_processed % 100 == 0 or len(rows) < batch_size:
            logger.info(
                "Progress: %d articles processed (offset=%d)", total_processed, offset
            )

    logger.info(
        "Backfill complete. Processed=%d skipped=%d dry_run=%s",
        total_processed,
        total_skipped,
        dry_run,
    )
    return total_processed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill topic assignments for articles missing from article_topic."
    )
    parser.add_argument(
        "--env-file",
        default="configs/aws/.env",
        help="Path to .env file with DB credentials (default: configs/aws/.env)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Articles to classify per DB batch (default: 200)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=CONFIDENCE_THRESHOLD,
        help=f"Cosine similarity threshold for 'General' fallback (default: {CONFIDENCE_THRESHOLD})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reclassify all articles, including those already in article_topic",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify but do not write to DB",
    )
    args = parser.parse_args()

    db_config = load_env(args.env_file)
    engine = get_engine(db_config)
    model = load_embedding_model()

    processed = run_backfill(
        engine=engine,
        model=model,
        threshold=args.threshold,
        batch_size=args.batch_size,
        force=args.force,
        dry_run=args.dry_run,
    )

    if processed == 0:
        logger.info("No articles needed backfilling — all articles already have a topic.")
    else:
        logger.info("Done. %d articles assigned a topic.", processed)


if __name__ == "__main__":
    main()
