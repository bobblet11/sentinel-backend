from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from microservices.api_gateway.services.job_service import JobService
from microservices.api_gateway.services.queue_service import QueueService
# microservices/api_gateway/routers/analysis.py
import logging
import asyncio
import hashlib
import random
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from utils.cache import get_cache, set_cache
from utils.helpers import httpx_encode, url_key
from utils.requests import fetch_json

# Allow running this module directly or via relative import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
router = APIRouter(prefix="/analysis", tags=["analysis"])

job_service = JobService()
queue_service = QueueService()


class AnalyzeRequest(BaseModel):
    title: str
    url: str
    content: str
    

Verdict = Literal["true", "mostly-true", "mixed", "mostly-false", "false", "unverified"]
Bias = Literal["left", "center-left", "center", "center-right", "right"]
Sentiment = Literal["positive", "neutral", "negative"]


def stable_rng(seed_str: str) -> random.Random:
    """Stable per-URL randomness so refreshing doesn't change values constantly."""
    h = hashlib.sha256((seed_str or "").encode("utf-8")).hexdigest()
    seed_int = int(h[:16], 16)
    return random.Random(seed_int)


def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def bias_from_score(score: int) -> Bias:
    if score <= -60:
        return "left"
    if score <= -20:
        return "center-left"
    if score < 20:
        return "center"
    if score < 60:
        return "center-right"
    return "right"


async def auto_complete_job(job_id: str, url: str, title: str, content: str, delay: int = 10):
    """Testing helper: Auto-complete job after delay with realistic mock data"""
    await asyncio.sleep(delay)
    
    rng = stable_rng(url or title)

    trust_score = rng.randint(35, 92)
    bias_score = rng.randint(-80, 80)
    bias_conf = rng.randint(55, 95)
    sentiment: Sentiment = rng.choice(["positive", "neutral", "negative"])

    overall_bias: Bias = bias_from_score(bias_score)

    # Keep content short-ish
    content_preview = content[:1800] if content else ""

    verdicts = ["true", "mostly-true", "mixed", "mostly-false", "false", "unverified"]

    def mk_claim(i: int, claim_text: str):
        v = rng.choice(verdicts)
        conf = clamp(rng.randint(45, 95), 0, 100)
        return {
            "id": str(i),
            "claim": claim_text,
            "verdict": v,
            "confidence": conf,
            "evidence": [
                {
                    "source": "On-page content",
                    "url": url or "https://example.com",
                    "excerpt": (content[:180] + "...") if content else "No page text captured.",
                },
                {
                    "source": "Secondary coverage (dummy)",
                    "url": "https://example.com/coverage",
                    "excerpt": "This is placeholder evidence for UI testing.",
                },
            ],
        }

    # Simple dummy claims derived from title
    key_claims = [
        mk_claim(1, f"{title} (primary claim)"),
        mk_claim(2, "A key statistic in the article is supported by sources."),
        mk_claim(3, "The article implies a causal relationship that may be debated."),
    ]

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    fact_checks = [
        {
            "id": "1",
            "source": "PolitiFact (dummy)",
            "url": "https://example.com/factcheck-1",
            "title": f"Fact-check: {title}",
            "verdict": rng.choice(["true", "mostly-true", "mixed", "mostly-false", "false"]),
            "publishedAt": now,
        },
        {
            "id": "2",
            "source": "Full Fact (dummy)",
            "url": "https://example.com/factcheck-2",
            "title": "Verification of key numbers mentioned in the article",
            "verdict": rng.choice(["true", "mostly-true", "mixed", "mostly-false", "false"]),
            "publishedAt": now,
        },
    ]

    related_articles = [
        {
            "id": "1",
            "title": f"Related: {title}",
            "source": "Example News",
            "url": "https://example.com/related-1",
            "bias": rng.choice(["left", "center-left", "center", "center-right", "right"]),
            "publishedAt": now,
            "excerpt": "Placeholder related article excerpt for UI testing.",
        },
        {
            "id": "2",
            "title": "Another angle on the same story",
            "source": "Another Outlet",
            "url": "https://example.com/related-2",
            "bias": rng.choice(["left", "center-left", "center", "center-right", "right"]),
            "publishedAt": now,
            "excerpt": "Placeholder excerpt focusing on a different framing.",
        },
    ]

    result = {
        "status": "COMPLETED",
        "article": {
            "title": title,
            "url": url,
            "content": content_preview,
            "source": "BBC News (dummy)",
            "author": "Jane Doe (dummy)",
            "publishedAt": now,
        },
        "trustScore": trust_score,
        "biasAnalysis": {
            "overallBias": overall_bias,
            "biasScore": bias_score,
            "confidence": bias_conf,
            "indicators": {
                "language": "Dummy: highlights loaded/charged language patterns for UI testing.",
                "sources": "Dummy: simulates whether multiple perspectives are cited.",
                "framing": "Dummy: simulates framing effects (what's emphasized vs downplayed).",
            },
            "sentiment": sentiment,
        },
        "keyClaims": key_claims,
        "factChecks": fact_checks,
        "relatedArticles": related_articles,
    }
    
    job_service.complete_job(job_id, result)
    logger.info(f"Auto-completed job {job_id} - url={url!r} title={title!r} trust={trust_score} bias={bias_score}")


@router.post("/analyze")
def analyze_article(req: AnalyzeRequest, background_tasks: BackgroundTasks):
    job = job_service.create_job()

    queue_service.publish_analysis_job(
        job_id=job.job_id,
        url=req.url,
        content=req.content,
        title=req.title
    )

    # For testing: auto-complete after 10 seconds
    background_tasks.add_task(auto_complete_job, job.job_id, req.url, req.title, req.content, 10)

    return {
        "job_id": job.job_id,
        "status": job.status
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = job_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "COMPLETED":
        return {
            "job_id": job.job_id,
            "status": job.status
        }

    return job.result
