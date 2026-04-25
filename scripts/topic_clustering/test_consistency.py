"""
test_consistency.py — Determinism and reproducibility test for BERTopic clustering.

Runs clustering twice with the same seed (expects 100% agreement) and once
with a different seed (logs a warning if agreement falls below 80%, but does
not fail — UMAP is sensitive to the random seed while the zero-shot portion
is largely deterministic).

Run from repo root:
    python -m scripts.topic_clustering.test_consistency --env-file configs/aws/.env
"""

import argparse
import logging
from typing import List, Tuple

from scripts.topic_clustering.poc_cluster import (PREDEFINED_TOPICS,
                                                  _build_docs, fetch_articles,
                                                  get_engine, load_env,
                                                  run_zero_shot_bertopic)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run_clustering_twice(
    engine,
    seed: int,
    min_topic_size: int = 5,
    zeroshot_threshold: float = 0.5,
) -> Tuple[List[int], List[int]]:
    """Run the full clustering pipeline twice with the same seed.

    Fetches articles once and runs BERTopic twice on identical inputs to
    verify deterministic behaviour.

    Args:
        engine: SQLAlchemy Engine connected to the Sentinel database.
        seed: Random seed to use for both runs.
        min_topic_size: HDBSCAN minimum cluster size.
        zeroshot_threshold: Zero-shot cosine similarity threshold.

    Returns:
        Tuple of (topics_run_1, topics_run_2).
    """
    df = fetch_articles(engine)
    if len(df) < 10:
        logger.warning("Fewer than 10 articles found; skipping consistency check.")
        return [], []

    docs = _build_docs(df)

    logger.info("Run 1 (seed=%d)…", seed)
    _, topics_a, _ = run_zero_shot_bertopic(
        docs=docs,
        predefined_topics=PREDEFINED_TOPICS,
        min_topic_size=min_topic_size,
        seed=seed,
        zeroshot_threshold=zeroshot_threshold,
    )

    logger.info("Run 2 (seed=%d)…", seed)
    _, topics_b, _ = run_zero_shot_bertopic(
        docs=docs,
        predefined_topics=PREDEFINED_TOPICS,
        min_topic_size=min_topic_size,
        seed=seed,
        zeroshot_threshold=zeroshot_threshold,
    )

    return list(topics_a), list(topics_b)


def compute_agreement(topics_a: List[int], topics_b: List[int]) -> float:
    """Compute the element-wise agreement percentage between two topic lists.

    Args:
        topics_a: Topic assignments from run A.
        topics_b: Topic assignments from run B.

    Returns:
        Fraction of matching assignments (0.0 – 1.0).
    """
    if len(topics_a) != len(topics_b):
        raise ValueError(
            f"Topic lists have different lengths: {len(topics_a)} vs {len(topics_b)}"
        )
    if not topics_a:
        return 1.0
    matches = sum(a == b for a, b in zip(topics_a, topics_b))
    return matches / len(topics_a)


def main() -> None:
    """Run determinism checks and print a report."""
    parser = argparse.ArgumentParser(
        description="Test determinism and reproducibility of BERTopic clustering."
    )
    parser.add_argument(
        "--env-file",
        default="configs/aws/.env",
        help="Path to .env file containing DB credentials (default: configs/aws/.env)",
    )
    parser.add_argument(
        "--min-topic-size",
        type=int,
        default=5,
        help="Minimum cluster size for HDBSCAN (default: 5)",
    )
    parser.add_argument(
        "--zeroshot-threshold",
        type=float,
        default=0.5,
        help="Minimum cosine similarity for zero-shot assignment (default: 0.5)",
    )
    args = parser.parse_args()

    db_config = load_env(args.env_file)
    engine = get_engine(db_config)

    print("")
    print("============================================")
    print("  TOPIC CLUSTERING — CONSISTENCY TESTS")
    print("============================================")

    # --- Check 1: exact determinism with same seed ---
    print("\n[CHECK 1] Same-seed determinism (seed=42, run twice)")
    topics_a, topics_b = run_clustering_twice(
        engine,
        seed=42,
        min_topic_size=args.min_topic_size,
        zeroshot_threshold=args.zeroshot_threshold,
    )

    if not topics_a:
        print("  SKIPPED — insufficient data.")
    else:
        agreement_same = compute_agreement(topics_a, topics_b)
        if agreement_same == 1.0:
            print(f"  PASS — 100% agreement across {len(topics_a)} articles.")
        else:
            disagreements = sum(a != b for a, b in zip(topics_a, topics_b))
            print(
                f"  FAIL — {disagreements}/{len(topics_a)} articles differ "
                f"({agreement_same*100:.1f}% agreement). "
                "BERTopic is not fully deterministic with this configuration."
            )

    # --- Check 2: near-determinism with different seeds ---
    print("\n[CHECK 2] Cross-seed agreement (seed=42 vs seed=99)")
    df = fetch_articles(engine)
    if len(df) < 10:
        print("  SKIPPED — insufficient data.")
    else:
        docs = _build_docs(df)

        logger.info("Run with seed=42…")
        _, topics_42, _ = run_zero_shot_bertopic(
            docs=docs,
            predefined_topics=PREDEFINED_TOPICS,
            min_topic_size=args.min_topic_size,
            seed=42,
            zeroshot_threshold=args.zeroshot_threshold,
        )

        logger.info("Run with seed=99…")
        _, topics_99, _ = run_zero_shot_bertopic(
            docs=docs,
            predefined_topics=PREDEFINED_TOPICS,
            min_topic_size=args.min_topic_size,
            seed=99,
            zeroshot_threshold=args.zeroshot_threshold,
        )

        agreement_cross = compute_agreement(list(topics_42), list(topics_99))
        pct = agreement_cross * 100
        if agreement_cross >= 0.80:
            print(f"  PASS — {pct:.1f}% cross-seed agreement ({len(topics_42)} articles).")
        else:
            logger.warning(
                "Cross-seed agreement is %.1f%% — below the 80%% guideline. "
                "UMAP is sensitive to random initialisation; the zero-shot portion "
                "should be stable but unsupervised clusters may vary.",
                pct,
            )
            print(
                f"  WARNING — {pct:.1f}% cross-seed agreement. "
                "This is below the 80% guideline (see log for details). "
                "Not a hard failure — UMAP variation is expected."
            )

    print("")
    print("============================================")
    print("")


if __name__ == "__main__":
    main()
