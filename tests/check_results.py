"""
Query the Sentinel DB and print all job results in a readable table format.

Usage:
    python tests/check_results.py                  # show all jobs
    python tests/check_results.py <uid>            # show one specific job

Connection defaults to the Docker network IP. Override with env vars:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
"""

import os
import subprocess
import sys

import psycopg2

# ---------------------------------------------------------------------------
# Connection config — override via env vars if needed
# ---------------------------------------------------------------------------
DB_HOST = os.getenv("POSTGRES_HOST", "172.18.0.4")
DB_PORT = int(os.getenv("POSTGRES_PORT", 5432))
DB_NAME = os.getenv("POSTGRES_DB", "sentinel_db")
DB_USER = os.getenv("POSTGRES_USER", "sentinel_user")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "Sentinel12345")

SEP  = "=" * 80
SEP2 = "-" * 80


def connect():
    try:
        return psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
            user=DB_USER, password=DB_PASS
        )
    except psycopg2.OperationalError as e:
        # Try to find the current postgres container IP automatically
        try:
            ip = subprocess.check_output(
                ["sudo", "docker", "inspect", "sentinel-postgres-container",
                 "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            return psycopg2.connect(
                host=ip, port=DB_PORT, dbname=DB_NAME,
                user=DB_USER, password=DB_PASS
            )
        except Exception:
            raise e


def get_jobs(cur, uid=None):
    query = """
        SELECT j.id, j.uid, j.status, j.type, j.created_at,
               a.id AS article_id, a.url, a.title,
               sa.bias_category, sa.bias_analysis_confidence,
               sa.sentiment_category, sa.sentiment_analysis_confidence
        FROM job j
        JOIN article a ON j.article_id = a.id
        LEFT JOIN sentiment_analysis sa ON a.sentiment_id = sa.id
    """
    if uid and uid.isdigit():
        cur.execute(query + " WHERE j.id = %s ORDER BY j.id DESC", (int(uid),))
    elif uid:
        cur.execute(query + " WHERE j.uid = %s ORDER BY j.id DESC", (uid,))
    else:
        cur.execute(query + " ORDER BY j.id DESC")
    return cur.fetchall()


def get_claims(cur, article_id):
    cur.execute("""
        SELECT c.decontextualised_claim, c.centrality_score,
               array_agg(e.name || '[' || COALESCE(e.type, '?') || ']') AS entities
        FROM claim c
        LEFT JOIN claim_to_entity cte ON cte.claim_id = c.id
        LEFT JOIN entity e ON e.id = cte.entity_id
        WHERE c.article_id = %s
        GROUP BY c.id, c.decontextualised_claim, c.centrality_score
        ORDER BY c.centrality_score DESC NULLS LAST
    """, (article_id,))
    return cur.fetchall()


def print_job(job, claims):
    j_id, uid, status, j_type, created_at, article_id, url, title, \
        bias_cat, bias_conf, sentiment_cat, sentiment_conf = job

    print(SEP)
    print(f"JOB #{j_id}  |  {uid}")
    print(SEP)
    print(f"  Status    : {status}  ({j_type})")
    print(f"  Created   : {created_at}")
    print(f"  Title     : {title or '(none)'}")
    print(f"  URL       : {url}")
    print(f"  Bias      : {bias_cat or 'N/A'}  (conf={bias_conf:.3f})" if bias_conf is not None else f"  Bias      : N/A")
    print(f"  Sentiment : {sentiment_cat or 'N/A'}" + (f"  (conf={sentiment_conf:.3f})" if sentiment_conf else ""))

    print()
    if not claims:
        print("  No claims stored.")
    else:
        print(f"  CLAIMS ({len(claims)} total)")
        for i, (claim_text, score, entities) in enumerate(claims, 1):
            score_str = f"{score:.3f}" if score is not None else "N/A"
            ent_list = [e for e in (entities or []) if e and not e.startswith("None")]
            ent_str = ", ".join(ent_list) if ent_list else "—"
            print(f"  {SEP2}")
            print(f"  [{i}] Score: {score_str}")
            print(f"  Claim   : {claim_text or ''}")
            print(f"  Entities: {ent_str}")
    print()


def main():
    uid_filter = sys.argv[1] if len(sys.argv) > 1 else None

    conn = connect()
    cur = conn.cursor()

    jobs = get_jobs(cur, uid=uid_filter)

    if not jobs:
        print("No jobs found." + (f" (uid={uid_filter})" if uid_filter else ""))
        return

    for job in jobs:
        article_id = job[5]
        claims = get_claims(cur, article_id)
        print_job(job, claims)

    print(f"Total jobs: {len(jobs)}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
