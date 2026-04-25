"""
test_edge_cases.py — Edge case handling tests for the topic clustering POC.

Validates:
1. Articles with null or empty titles are excluded from clustering input.
2. Articles with very long titles are truncated safely by _build_docs.
3. An empty corpus is handled gracefully (no crash, clean exit).
4. fetch_articles returns a non-empty DataFrame against a live DB.
5. All returned titles are non-null and non-empty strings.

Run from repo root:
    python -m scripts.topic_clustering.test_edge_cases --env-file configs/aws/.env
"""

import argparse
import logging
import sys
from unittest.mock import MagicMock, patch

import pandas as pd
from sqlalchemy import text

from scripts.topic_clustering.poc_cluster import (
    _build_docs,
    fetch_articles,
    get_engine,
    load_env,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def test_null_title_articles_excluded(engine) -> bool:
    """Assert that articles with null or empty titles are absent from results.

    The SQL query filters WHERE title IS NOT NULL AND title != '', so these
    articles must never appear in the clustering input.

    Args:
        engine: SQLAlchemy Engine connected to the Sentinel database.

    Returns:
        True if the check passes, False otherwise.
    """
    logger.info(
        "test_null_title_articles_excluded: querying for null/empty-title articles…"
    )
    null_title_sql = text(
        "SELECT COUNT(*) FROM article WHERE title IS NULL OR title = ''"
    )
    with engine.connect() as conn:
        count = conn.execute(null_title_sql).scalar()
    logger.info("Articles with null/empty title in DB: %d", count)

    df = fetch_articles(engine)
    if df.empty:
        logger.info("DataFrame is empty — trivially passes.")
        return True

    has_null = df["title"].isnull().any() or (df["title"] == "").any()
    if has_null:
        logger.error("FAIL: null or empty titles found in fetch_articles output.")
        return False

    logger.info("PASS: no null or empty titles in clustering input.")
    return True


def test_long_title_truncation() -> bool:
    """Verify that _build_docs truncates titles longer than 300 characters.

    Constructs a synthetic DataFrame with one very long title and checks
    that the resulting doc string is at most 300 characters.

    Returns:
        True if truncation is applied correctly, False otherwise.
    """
    logger.info(
        "test_long_title_truncation: testing _build_docs with a 500-char title…"
    )
    long_title = "A" * 500
    df = pd.DataFrame({"title": [long_title], "url": ["http://example.com"]})
    docs = _build_docs(df)

    if len(docs) != 1:
        logger.error("FAIL: expected 1 doc, got %d", len(docs))
        return False

    if len(docs[0]) > 300:
        logger.error("FAIL: doc string is %d chars, expected <= 300", len(docs[0]))
        return False

    logger.info("PASS: long title truncated to %d chars.", len(docs[0]))
    return True


def test_empty_corpus_handling() -> bool:
    """Verify the early-exit path when fetch_articles returns an empty DataFrame.

    Patches fetch_articles to return an empty DataFrame and calls main(),
    verifying that it exits cleanly with code 0.

    Returns:
        True if main() exits cleanly (SystemExit(0) or no crash), False otherwise.
    """
    logger.info("test_empty_corpus_handling: testing early-exit on empty corpus…")

    import scripts.topic_clustering.poc_cluster as poc  # noqa: PLC0415

    empty_df = pd.DataFrame(columns=["id", "title", "url"])

    with patch.object(poc, "fetch_articles", return_value=empty_df):
        with patch.object(
            poc,
            "load_env",
            return_value={
                "host": "localhost",
                "port": "5432",
                "db": "sentinel",
                "user": "sentinel",
                "password": "",
                "sslmode": "disable",
            },
        ):
            with patch.object(poc, "get_engine", return_value=MagicMock()):
                import sys as _sys  # noqa: PLC0415

                old_argv = _sys.argv
                _sys.argv = ["poc_cluster"]
                try:
                    poc.main()
                    logger.info("PASS: main() returned without crash on empty corpus.")
                    return True
                except SystemExit as exc:
                    if exc.code == 0:
                        logger.info(
                            "PASS: main() exited cleanly (code 0) on empty corpus."
                        )
                        return True
                    logger.error("FAIL: main() exited with non-zero code %s.", exc.code)
                    return False
                except Exception as exc:  # noqa: BLE001
                    logger.error("FAIL: main() raised unexpected exception: %s", exc)
                    return False
                finally:
                    _sys.argv = old_argv


def test_fetch_articles_live(engine) -> bool:
    """Verify fetch_articles returns a non-empty DataFrame against the live DB.

    Args:
        engine: SQLAlchemy Engine connected to the Sentinel database.

    Returns:
        True if at least one article is returned with id, title, url columns.
    """
    logger.info("test_fetch_articles_live: calling fetch_articles against live DB…")
    df = fetch_articles(engine)

    if df.empty:
        logger.error("FAIL: fetch_articles returned an empty DataFrame.")
        return False

    for col in ("id", "title", "url"):
        if col not in df.columns:
            logger.error(
                "FAIL: missing expected column '%s' in fetch_articles output.", col
            )
            return False

    logger.info(
        "PASS: fetch_articles returned %d articles with expected columns.", len(df)
    )
    return True


def test_all_titles_are_strings(engine) -> bool:
    """Verify that every title returned by fetch_articles is a non-null string.

    Args:
        engine: SQLAlchemy Engine connected to the Sentinel database.

    Returns:
        True if all titles are non-null non-empty strings, False otherwise.
    """
    logger.info("test_all_titles_are_strings: checking title column integrity…")
    df = fetch_articles(engine)

    if df.empty:
        logger.info("DataFrame is empty — trivially passes.")
        return True

    null_count = df["title"].isnull().sum()
    empty_count = (df["title"] == "").sum()

    if null_count > 0 or empty_count > 0:
        logger.error(
            "FAIL: %d null titles and %d empty titles found.", null_count, empty_count
        )
        return False

    logger.info("PASS: all %d titles are non-null, non-empty strings.", len(df))
    return True


def main() -> None:
    """Run all edge case tests and print a summary. Exit 1 if any test fails."""
    parser = argparse.ArgumentParser(
        description="Edge case tests for the topic clustering POC."
    )
    parser.add_argument(
        "--env-file",
        default="configs/aws/.env",
        help="Path to .env file containing DB credentials (default: configs/aws/.env)",
    )
    args = parser.parse_args()

    db_config = load_env(args.env_file)
    engine = get_engine(db_config)

    print("")
    print("============================================")
    print("  TOPIC CLUSTERING — EDGE CASE TESTS")
    print("============================================")

    tests = [
        (
            "Null/empty title articles excluded",
            lambda: test_null_title_articles_excluded(engine),
        ),
        ("Long title truncation", test_long_title_truncation),
        ("Empty corpus early exit", test_empty_corpus_handling),
        ("fetch_articles live DB check", lambda: test_fetch_articles_live(engine)),
        ("All titles are valid strings", lambda: test_all_titles_are_strings(engine)),
    ]

    results = []
    for name, fn in tests:
        logger.info("Running: %s", name)
        try:
            passed = fn()
        except Exception as exc:  # noqa: BLE001
            logger.error("Test '%s' raised an unexpected exception: %s", name, exc)
            passed = False
        status = "PASS" if passed else "FAIL"
        results.append((name, passed))
        print(f"\n[{status}] {name}")

    print("")
    total = len(results)
    passed_count = sum(1 for _, p in results if p)
    print(f"Results: {passed_count}/{total} passed")
    print("============================================")
    print("")

    if passed_count < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
