"""
test_quality.py — Topic assignment quality validation.

Loads the output of poc_cluster.py (results.json and topic_info.json) and
runs 5 automated quality checks, printing a report to stdout.

Exits with code 0 if all checks pass, 1 if any fail.

Run from repo root:
    python -m scripts.topic_clustering.test_quality \\
        --results-file scripts/topic_clustering/output/results.json \\
        --topic-info-file scripts/topic_clustering/output/topic_info.json
"""

import argparse
import json
import logging
import sys
from typing import List

import numpy as np

from scripts.topic_clustering.poc_cluster import PREDEFINED_TOPICS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def load_results(results_path: str) -> List[dict]:
    """Load article clustering results from a JSON file.

    Args:
        results_path: Path to results.json produced by poc_cluster.py.

    Returns:
        List of result dicts.
    """
    with open(results_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    logger.info("Loaded %d results from %s", len(data), results_path)
    return data


def load_topic_info(topic_info_path: str) -> List[dict]:
    """Load BERTopic topic_info from a JSON file.

    Args:
        topic_info_path: Path to topic_info.json produced by poc_cluster.py.

    Returns:
        List of topic info dicts.
    """
    with open(topic_info_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    logger.info("Loaded %d topic entries from %s", len(data), topic_info_path)
    return data


def check_confidence_distribution(results: List[dict]) -> dict:
    """Check that the majority of articles have reasonable confidence scores.

    Flags a failure if more than 50% of non-outlier articles have confidence
    below 0.3, which would indicate the model is largely uncertain.

    Args:
        results: List of result dicts.

    Returns:
        Dict with keys: name, passed, details.
    """
    non_outlier = [r for r in results if r["topic_id"] != -1]
    if not non_outlier:
        return {
            "name": "Confidence Distribution",
            "passed": False,
            "details": "No non-outlier articles found — cannot evaluate confidence.",
        }

    confidences = [r["confidence"] for r in non_outlier]
    low_conf = sum(1 for c in confidences if c < 0.3)
    low_pct = low_conf / len(confidences) * 100

    arr = np.array(confidences)
    details = (
        f"n={len(confidences)}, mean={arr.mean():.3f}, median={float(np.median(arr)):.3f}, "
        f"min={arr.min():.3f}, max={arr.max():.3f}, "
        f"low_confidence(<0.3): {low_conf} ({low_pct:.1f}%)"
    )
    passed = low_pct <= 50.0
    return {
        "name": "Confidence Distribution",
        "passed": passed,
        "details": details
        + ("" if passed else " [FAIL: >50% of articles have confidence < 0.3]"),
    }


def check_topic_coverage(results: List[dict], predefined: List[str]) -> dict:
    """Verify that each predefined topic has at least one article assigned.

    Args:
        results: List of result dicts.
        predefined: List of expected predefined topic label strings.

    Returns:
        Dict with keys: name, passed, details.
    """
    assigned_labels = {r["topic_label"].lower() for r in results if r["is_predefined"]}
    missing = [t for t in predefined if t.lower() not in assigned_labels]
    covered = [t for t in predefined if t.lower() in assigned_labels]

    details = f"Covered topics: {covered}. " + (
        f"Missing topics (zero articles): {missing}"
        if missing
        else "All predefined topics covered."
    )
    passed = len(missing) == 0
    return {
        "name": "Topic Coverage",
        "passed": passed,
        "details": details,
    }


def check_outlier_ratio(results: List[dict]) -> dict:
    """Check that the proportion of outlier articles is not excessive.

    Flags a failure if more than 30% of articles are assigned to topic -1.

    Args:
        results: List of result dicts.

    Returns:
        Dict with keys: name, passed, details.
    """
    total = len(results)
    if total == 0:
        return {
            "name": "Outlier Ratio",
            "passed": False,
            "details": "No results — cannot evaluate outlier ratio.",
        }

    outlier_count = sum(1 for r in results if r["topic_id"] == -1)
    outlier_pct = outlier_count / total * 100

    details = f"{outlier_count}/{total} articles are outliers ({outlier_pct:.1f}%)"
    passed = outlier_pct <= 30.0
    return {
        "name": "Outlier Ratio",
        "passed": passed,
        "details": details + ("" if passed else " [FAIL: outlier ratio exceeds 30%]"),
    }


def check_discovered_topics(topic_info: List[dict], results: List[dict]) -> dict:
    """Inspect any topics discovered beyond the predefined 8.

    This check always passes — its purpose is to surface discovered topics
    for manual review, not to gate on their presence or absence.

    Args:
        topic_info: List of topic info dicts from topic_info.json.
        results: List of result dicts.

    Returns:
        Dict with keys: name, passed, details.
    """
    predefined_lower = {t.lower() for t in PREDEFINED_TOPICS}
    discovered = [
        ti
        for ti in topic_info
        if ti.get("Topic", -1) != -1
        and str(ti.get("Name", "")).lower() not in predefined_lower
    ]

    if not discovered:
        details = "No discovered (unsupervised) topics found beyond the predefined 8."
    else:
        parts = []
        for ti in discovered:
            tid = ti.get("Topic")
            tname = ti.get("Name", "")
            count = sum(1 for r in results if r["topic_id"] == tid)
            parts.append(f"  Topic {tid} '{tname}': {count} articles")
        details = f"{len(discovered)} discovered topic(s):\n" + "\n".join(parts)

    return {
        "name": "Discovered Topics Sanity",
        "passed": True,
        "details": details,
    }


def spot_check_titles(results: List[dict], n_samples: int = 5) -> None:
    """Print sample article titles for each predefined topic for manual review.

    Args:
        results: List of result dicts.
        n_samples: Number of sample titles to print per topic.
    """
    print("")
    print("--- Spot Check: Sample Titles per Predefined Topic ---")
    for topic in PREDEFINED_TOPICS:
        matching = [
            r
            for r in results
            if r["is_predefined"] and r["topic_label"].lower() == topic.lower()
        ]
        samples = matching[:n_samples]
        print(f"\n  {topic} ({len(matching)} total):")
        if not samples:
            print("    (no articles assigned)")
        for r in samples:
            title = r["title"] or "(no title)"
            print(f"    - {title[:100]}")
    print("")


def main() -> None:
    """Run all quality checks and print a report. Exit 1 if any check fails."""
    parser = argparse.ArgumentParser(
        description="Validate topic clustering quality from poc_cluster.py output."
    )
    parser.add_argument(
        "--results-file",
        default="scripts/topic_clustering/output/results.json",
        help="Path to results.json (default: scripts/topic_clustering/output/results.json)",
    )
    parser.add_argument(
        "--topic-info-file",
        default="scripts/topic_clustering/output/topic_info.json",
        help="Path to topic_info.json (default: scripts/topic_clustering/output/topic_info.json)",
    )
    args = parser.parse_args()

    results = load_results(args.results_file)
    topic_info = load_topic_info(args.topic_info_file)

    checks = [
        check_confidence_distribution(results),
        check_topic_coverage(results, PREDEFINED_TOPICS),
        check_outlier_ratio(results),
        check_discovered_topics(topic_info, results),
    ]

    print("")
    print("============================================")
    print("  TOPIC QUALITY VALIDATION REPORT")
    print("============================================")
    all_passed = True
    for check in checks:
        status = "PASS" if check["passed"] else "FAIL"
        if not check["passed"]:
            all_passed = False
        print(f"\n[{status}] {check['name']}")
        print(f"  {check['details']}")

    # Spot check titles (always runs, informational only)
    spot_check_titles(results)

    print("============================================")
    if all_passed:
        print("All checks PASSED.")
    else:
        print("One or more checks FAILED. Review details above.")
    print("============================================")
    print("")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
