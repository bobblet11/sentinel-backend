"""
poc_cluster.py — Sentence-similarity topic classification POC.

Connects to the Sentinel PostgreSQL database, fetches article titles plus
the top 4 claims by centrality score, then classifies each article into one
of 8 predefined topic categories (Politics, World, Technology, Health,
Science, Business, Entertainment, Sports) using cosine similarity against
sentence-based topic description embeddings via sentence-transformers.
Articles scoring below CONFIDENCE_THRESHOLD against all topics are labelled
"General".

Run from repo root:
    python -m scripts.topic_clustering.poc_cluster --env-file configs/local/.env
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple  # noqa: F401 (Tuple used in classify signature)

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PREDEFINED_TOPICS: List[str] = [
    "Politics",
    "World",
    "Technology",
    "Health",
    "Science",
    "Business",
    "Entertainment",
    "Sports",
    "General",
]

# Articles whose best cosine similarity to any topic falls below this threshold
# are assigned "General" rather than forcing a wrong predefined label.
CONFIDENCE_THRESHOLD: float = 0.15

# Sentence-based descriptions for cosine-similarity classification.
# Written as natural language so all-mpnet-base-v2 (a sentence-transformer) can
# encode them coherently.  "General" is intentionally excluded here — it is
# assigned via the threshold fallback, not via competition, which prevents the
# broad General description from stealing articles that clearly belong elsewhere.
TOPIC_DESCRIPTIONS: Dict[str, str] = {
    "Politics": (
        "Politicians debated new legislation in parliament and congress. "
        "The president signed an executive order affecting government policy. "
        "Voters headed to the polls in the national election. "
        "The prime minister announced a major cabinet reshuffle. "
        "A federal court ruling challenged the administration's legal authority. "
        "The senator faced calls to resign following the ethics investigation. "
        "Political parties launched their campaign platforms ahead of the vote."
    ),
    "World": (
        "International diplomats met at the United Nations to discuss the ongoing conflict. "
        "Military forces clashed along the disputed border region. "
        "An airman was rescued after his jet was shot down during the military operation. "
        "Refugees fleeing the humanitarian crisis sought asylum in neighbouring countries. "
        "Foreign ministers held emergency talks over rising geopolitical tensions. "
        "Troops were deployed to support peacekeeping efforts in the conflict zone. "
        "The war has caused widespread civilian casualties and displacement."
    ),
    "Technology": (
        "The tech startup launched a new artificial intelligence product at the conference. "
        "Researchers published a breakthrough in machine learning and deep neural networks. "
        "A major cybersecurity breach exposed millions of user accounts and leaked private data. "
        "Apple and Google announced new software and hardware features for their devices. "
        "The semiconductor company unveiled its next-generation chip architecture. "
        "The robotics company demonstrated its latest autonomous vehicle system."
    ),
    "Health": (
        "Doctors reported a rise in cases of the infectious disease across the region. "
        "The clinical trial showed promising results for the new cancer treatment. "
        "Public health officials warned about the spread of the virus. "
        "The hospital introduced a new surgical procedure for cardiac patients. "
        "Mental health services are struggling to meet growing demand. "
        "A product recall was issued after contamination risks were identified."
    ),
    "Science": (
        "Scientists discovered a new species in the depths of the Amazon rainforest. "
        "The space agency launched a probe to study the surface of Mars. "
        "Climate researchers warned that global temperatures are rising faster than predicted. "
        "The study published in Nature revealed new insights into human evolution. "
        "Astronomers detected a rare cosmic phenomenon using the James Webb telescope. "
        "Geologists mapped a previously unknown fault line beneath the ocean floor."
    ),
    "Business": (
        "The company reported record quarterly earnings, beating market expectations. "
        "Central banks raised interest rates to combat rising inflation. "
        "Stock markets fell sharply after the trade war escalated. "
        "The merger between the two corporations was approved by regulators. "
        "Unemployment figures rose as the economy slowed and businesses cut jobs. "
        "The retail chain announced it would close dozens of stores nationwide."
    ),
    "Entertainment": (
        "The film won three Academy Awards at the Hollywood ceremony. "
        "The pop star's new album debuted at number one on the charts. "
        "The streaming service announced a major new television series. "
        "Critics praised the director's latest movie at the film festival. "
        "The celebrity couple announced their divorce in a joint statement. "
        "The band cancelled their world tour citing creative differences."
    ),
    "Sports": (
        "The team won the championship after a dramatic final match. "
        "The footballer scored a hat-trick to lead his side to victory. "
        "The Olympic athlete broke the world record in the 100-metre sprint. "
        "The coach was sacked after a string of poor results this season. "
        "The tennis player defeated the top seed to reach the grand slam final. "
        "The rugby side clinched promotion with a last-minute try. "
        "The premier league club announced a new signing from the transfer window. "
        "The cricket team dominated the test series with an emphatic innings victory."
    ),
}


_SQL_FETCH_ARTICLES = text(
    """
    SELECT a.id, a.title, a.url, top_c.top_claims
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
    """
)


def load_env(env_file: str = "configs/aws/.env") -> dict:
    """Load DB connection params from a .env file or the process environment.

    Args:
        env_file: Path to the .env file, relative to the current working
            directory.  Falls back to environment variables if the file does
            not exist.

    Returns:
        Dict with keys: host, port, db, user, password, sslmode.
    """
    env_path = Path(env_file)
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
        logger.info("Loaded env from %s", env_path)
    else:
        logger.warning(
            ".env file not found at %s — relying on process environment", env_path
        )

    return {
        "host": "localhost",
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "db": os.environ.get("POSTGRES_DB", "sentinel"),
        "user": os.environ.get("POSTGRES_USER", "sentinel"),
        "password": os.environ.get("POSTGRES_PASSWORD", ""),
        "sslmode": os.environ.get("POSTGRES_SSLMODE", "disable"),
    }


def get_engine(db_config: dict) -> Engine:
    """Create a SQLAlchemy engine from a config dict.

    Args:
        db_config: Dict with keys host, port, db, user, password, sslmode.

    Returns:
        A SQLAlchemy Engine configured with pool_pre_ping=True.
    """
    url = (
        "postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
        "?sslmode={sslmode}"
    ).format(**db_config)

    engine = create_engine(url, pool_pre_ping=True)
    logger.info(
        "Created engine for %s:%s/%s",
        db_config["host"],
        db_config["port"],
        db_config["db"],
    )
    return engine


def fetch_articles(engine: Engine) -> pd.DataFrame:
    """Fetch articles with their title and top 2 claims by centrality score.

    Articles without titles are excluded. The top_claims column contains up
    to 2 decontextualised claims concatenated with a space, or None if the
    article has no claims.

    Args:
        engine: A SQLAlchemy Engine connected to the Sentinel database.

    Returns:
        DataFrame with columns: id, title, url, top_claims.
    """
    logger.info("Fetching articles with titles and top claims from DB…")
    with engine.connect() as conn:
        result = conn.execute(_SQL_FETCH_ARTICLES)
        rows = result.fetchall()
        columns = list(result.keys())

    df = pd.DataFrame(rows, columns=columns)
    claims_present = df["top_claims"].notna().sum()
    logger.info(
        "Articles fetched: %d (%d with at least one claim)", len(df), claims_present
    )
    return df


def build_results(
    df: "pd.DataFrame",
    topic_labels: List[str],
    confidences: List[float],
) -> List[dict]:
    """Merge topic assignments with article metadata.

    Args:
        df: DataFrame from fetch_articles (columns: id, title, url).
        topic_labels: Per-article topic label strings (one of PREDEFINED_TOPICS).
        confidences: Per-article cosine similarity scores.

    Returns:
        List of result dicts, one per article.
    """
    general_idx = PREDEFINED_TOPICS.index("General")
    results: List[dict] = []
    for i, (_, row) in enumerate(df.iterrows()):
        label = topic_labels[i]
        # Stage 2 sub-labels (Crime, Lifestyle…) map to the General topic_id
        topic_id = (
            PREDEFINED_TOPICS.index(label) if label in PREDEFINED_TOPICS else general_idx
        )
        results.append(
            {
                "article_id": int(row["id"]),
                "title": str(row["title"]) if row["title"] is not None else "",
                "url": str(row["url"]),
                "topic_id": topic_id,
                "topic_label": label,
                "confidence": round(confidences[i], 6),
                "is_predefined": True,
            }
        )
    return results


def print_quality_summary(results: List[dict]) -> None:
    """Print a formatted quality summary to stdout.

    Args:
        results: List of result dicts from build_results.
    """
    total = len(results)
    if total == 0:
        print("No results to summarise.")
        return

    from collections import Counter

    topic_counts: Counter = Counter(r["topic_label"] for r in results)
    confidences = [r["confidence"] for r in results]
    mean_conf = float(np.mean(confidences))
    median_conf = float(np.median(confidences))
    min_conf = float(np.min(confidences))
    max_conf = float(np.max(confidences))

    print("")
    print("============================================")
    print("  TOPIC CLUSTERING POC — QUALITY SUMMARY")
    print("============================================")
    print("")
    print(f"Total articles processed: {total}")
    print("")
    print("--- Topic Distribution ---")
    for topic in PREDEFINED_TOPICS:
        count = topic_counts.get(topic, 0)
        pct = count / total * 100
        print(f"  {topic:<20}: {count:>4} ({pct:5.1f}%)")

    print("")
    print("--- Confidence Stats (cosine similarity) ---")
    print(f"  Mean  : {mean_conf:.3f}")
    print(f"  Median: {median_conf:.3f}")
    print(f"  Min   : {min_conf:.3f}")
    print(f"  Max   : {max_conf:.3f}")
    print(f"  Threshold for 'General' fallback: {CONFIDENCE_THRESHOLD}")
    general_count = topic_counts.get("General", 0)
    print(f"  Articles below threshold → General: {general_count} ({general_count/total*100:.1f}%)")
    print("")
    print("  All articles assigned to predefined topics (0 outliers)")
    print("")
    print("============================================")
    print("")


def save_results(results: List[dict], output_dir: str) -> None:
    """Save clustering results to JSON, CSV, and topic_info JSON files.

    Args:
        results: List of result dicts from build_results.
        output_dir: Directory path where output files will be written.
            Created if it does not exist.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    results_json_path = out_path / "results.json"
    with open(results_json_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
    logger.info("Saved results.json (%d records) to %s", len(results), results_json_path)

    results_csv_path = out_path / "results.csv"
    pd.DataFrame(results).to_csv(results_csv_path, index=False)
    logger.info("Saved results.csv to %s", results_csv_path)


def save_topic_info(results: List[dict], output_dir: str) -> None:
    """Save per-topic article counts to topic_info.json.

    Args:
        results: List of result dicts from build_results.
        output_dir: Directory path where output files will be written.
    """
    from collections import Counter

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    counts: Counter = Counter(r["topic_label"] for r in results)
    topic_info = [
        {
            "topic_id": PREDEFINED_TOPICS.index(t),
            "Name": t,
            "Count": counts.get(t, 0),
            "is_predefined": True,
        }
        for t in PREDEFINED_TOPICS
    ]
    topic_info_path = out_path / "topic_info.json"
    with open(topic_info_path, "w", encoding="utf-8") as fh:
        json.dump(topic_info, fh, indent=2, ensure_ascii=False)
    logger.info("Saved topic_info.json (%d topics) to %s", len(topic_info), topic_info_path)


def _build_docs(df: "pd.DataFrame") -> List[str]:
    """Build the text corpus from article titles and top claims.

    Each document is the article title followed by up to 2 top claims
    (by centrality score), giving the classifier richer signal than the
    title alone while keeping documents short.

    Args:
        df: DataFrame with columns 'title' and 'top_claims'.

    Returns:
        List of document strings, each capped at 400 characters.
    """
    docs: List[str] = []
    for _, row in df.iterrows():
        title = str(row["title"]).strip() if row["title"] is not None else ""
        claims = str(row["top_claims"]).strip() if row["top_claims"] is not None else ""
        doc = (title + (" " + claims if claims else "")).strip()
        docs.append(doc[:600])
    return docs


def _clean_doc(doc: str) -> str:
    """Strip source bylines and privacy boilerplate from a document string.

    Removes patterns like "- BBC News", "| CBC Sports", and cookie/privacy
    consent text scraped from video pages.

    Args:
        doc: Raw document string (title + claims).

    Returns:
        Cleaned document string.
    """
    import re

    # Strip trailing source bylines: " - BBC News", " | Euronews", etc.
    doc = re.sub(
        r"\s*[-|]\s*(BBC|CBC|ABC|CBS|NBC|NPR|Reuters|AP|CNN)[^\n]*$",
        "",
        doc,
        flags=re.IGNORECASE,
    )
    # Strip cookie/privacy boilerplate from scraped video pages
    _PRIVACY_TRIGGERS = ("cookie", "browsing", "consent", "privacy policy", "copy/paste the link")
    if any(t in doc.lower() for t in _PRIVACY_TRIGGERS):
        first_sent = re.split(r"(?<=[.!?])\s", doc)[0]
        doc = first_sent[:120]
    # Blank out news digest/bulletin titles — they have no topic signal and land
    # unpredictably near topic centroids.  Emptying them forces a low similarity
    # score across all topics, so they fall through to "General" via the threshold.
    _DIGEST_PATTERNS = (
        r"^latest news bulletin\b",
        r"^(morning|afternoon|evening) (mail|update|briefing|bulletin)\b",
        r"^(today('s)?|tonight('s)?) (top )?headlines?\b",
        r"^news (roundup|wrap|digest)\b",
    )
    if any(re.search(p, doc.lower()) for p in _DIGEST_PATTERNS):
        return ""
    return doc.strip()


def load_embedding_model() -> "SentenceTransformer":  # noqa: F821
    """Load and return the shared sentence-transformers model.

    Returns:
        A SentenceTransformer instance loaded onto the best available device.
    """
    import os  # noqa: PLC0415

    # configs/aws/.env sets HF_HOME/TRANSFORMERS_CACHE to /opt/sentinel (a Docker-only path).
    # Override to a local writable cache before importing sentence_transformers so that
    # HuggingFace resolves the model from the default user cache instead.
    local_hf_cache = os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
    os.environ["HF_HOME"] = local_hf_cache
    os.environ["TRANSFORMERS_CACHE"] = local_hf_cache

    import torch  # noqa: PLC0415
    from sentence_transformers import SentenceTransformer  # noqa: PLC0415

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("Loading sentence-transformers model (device=%s)…", device)
    logger.info("HuggingFace cache: %s", local_hf_cache)
    return SentenceTransformer("sentence-transformers/all-mpnet-base-v2", device=device)


def classify_articles_by_similarity(
    docs: List[str],
    topic_descriptions: Dict[str, str],
    model: "SentenceTransformer",  # noqa: F821
) -> Tuple[List[str], List[float], np.ndarray]:
    """Assign each document to the nearest predefined topic via cosine similarity.

    Encodes both the topic descriptions and documents using the provided
    sentence-transformers model, then assigns each document to the topic with
    the highest cosine similarity score.  Documents below CONFIDENCE_THRESHOLD
    are labelled "General" for Stage 2 reclassification.

    Args:
        docs: List of article document strings.
        topic_descriptions: Mapping of topic name → rich description string.
        model: Pre-loaded SentenceTransformer model (shared with Stage 2).

    Returns:
        Tuple of (labels, confidences, doc_embs) — labels and confidence per
        document, plus the L2-normalised document embedding matrix for reuse.
    """
    topic_names = list(topic_descriptions.keys())
    description_texts = [topic_descriptions[t] for t in topic_names]

    logger.info("Encoding %d topic descriptions…", len(topic_names))
    topic_embs = model.encode(
        description_texts, normalize_embeddings=True, show_progress_bar=False
    )

    logger.info("Encoding %d article documents…", len(docs))
    doc_embs = model.encode(
        docs, normalize_embeddings=True, show_progress_bar=True, batch_size=64
    )

    # Cosine similarity = dot product of L2-normalised vectors → (n_docs, n_topics)
    sims = doc_embs @ topic_embs.T

    labels: List[str] = []
    confidences: List[float] = []
    for i, sim_row in enumerate(sims):
        # Empty docs (e.g. bulletin/digest titles stripped by _clean_doc) have no
        # topic signal — force "General" regardless of where the zero-length
        # embedding happens to land.
        if not docs[i]:
            labels.append("General")
            confidences.append(0.0)
            continue
        best_idx = int(np.argmax(sim_row))
        best_score = float(sim_row[best_idx])
        if best_score < CONFIDENCE_THRESHOLD:
            labels.append("General")
        else:
            labels.append(topic_names[best_idx])
        confidences.append(best_score)

    return labels, confidences, doc_embs



def main() -> None:
    """Entry point for the sentence-similarity topic classification POC.

    Orchestrates: env loading, DB fetch, document cleaning, cosine-similarity
    topic classification, result building, quality summary printing, and file output.
    """
    parser = argparse.ArgumentParser(
        description="Sentence-similarity topic classification POC for Sentinel articles."
    )
    parser.add_argument(
        "--env-file",
        default="configs/local/.env",
        help="Path to .env file containing DB credentials (default: configs/local/.env)",
    )
    parser.add_argument(
        "--output-dir",
        default="scripts/topic_clustering/output",
        help="Output directory for results files (default: scripts/topic_clustering/output)",
    )
    # Legacy flags kept for backward compatibility with existing test invocations
    parser.add_argument("--min-topic-size", type=int, default=5, help=argparse.SUPPRESS)
    parser.add_argument("--seed", type=int, default=42, help=argparse.SUPPRESS)
    parser.add_argument("--zeroshot-threshold", type=float, default=0.5, help=argparse.SUPPRESS)
    # --seed is unused (Stage 2 removed) but kept to avoid breaking existing callers
    args = parser.parse_args()

    # Step 1: Load environment and build DB engine
    db_config = load_env(args.env_file)
    engine = get_engine(db_config)

    # Step 2: Fetch articles
    df = fetch_articles(engine)

    # Step 3: Early exit if too few articles
    if len(df) < 10:
        logger.warning(
            "Only %d articles with titles found — minimum required is 10.",
            len(df),
        )
        print(
            f"\nInsufficient data: only {len(df)} article(s) with titles found. "
            f"Need at least 10 to classify. Exiting.\n"
        )
        sys.exit(0)

    # Step 4: Build and clean document strings from titles + top claims
    docs = [_clean_doc(d) for d in _build_docs(df)]
    logger.info("Built and cleaned %d document strings for classification", len(docs))

    # Step 5: Load embedding model
    model = load_embedding_model()

    # Step 6: Cosine-similarity classification against predefined topics.
    # Articles scoring below CONFIDENCE_THRESHOLD are assigned "General".
    topic_labels, confidences, _doc_embs = classify_articles_by_similarity(
        docs, TOPIC_DESCRIPTIONS, model
    )

    # Step 7: Build result records
    results = build_results(df, topic_labels, confidences)

    # Step 9: Print quality summary
    print_quality_summary(results)

    # Step 10: Save outputs
    save_results(results, args.output_dir)
    save_topic_info(results, args.output_dir)

    logger.info("Done. Results written to %s/", args.output_dir)


if __name__ == "__main__":
    main()
