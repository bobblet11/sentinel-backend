from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.exc import IntegrityError
from common.models.api.dtos.job import JobStatus
from common.redis_client.hash_store import RedisHashStore
from microservices.api.app.core.config import HASH_STORE_NAMESPACE
from microservices.api.app.crud.crud_article import create_article, get_article_by_url
from microservices.api.app.db.session import get_db
from microservices.api.app.services.news_outlet import get_news_outlet
from microservices.api.app.dtos.job import JobCreate, JobResponse, JobType
from microservices.api.app.crud.crud_job import create_job, get_job, get_latest_job_for_article
from microservices.api.app.models.article import Article
from microservices.api.app.models.job import Job
from microservices.api.app.services.redis_queue import publish_job
from sqlalchemy.orm import Session
from uuid import UUID
import asyncio
from typing import Dict, Any, List, cast
import logging

router = APIRouter()
result_hash_store = RedisHashStore(hash_namespace=HASH_STORE_NAMESPACE)
logger = logging.getLogger(__name__)


def _build_bias_analysis(bias_profile: Dict[str, Any] | None) -> Dict[str, Any]:
    if not bias_profile:
        return {
            "overallBias": "center",
            "biasScore": 0,
            "confidence": 0,
            "sentiment": "neutral",
            "indicators": {
                "language": "No bias profile available",
                "sources": "No source bias signal available",
                "framing": "No framing signal available",
            },
        }

    bias_category = str(bias_profile.get("bias_category") or "center").lower()
    sentiment_category = str(bias_profile.get("sentiment_category") or "neutral").lower()

    bias_score_01 = float(bias_profile.get("bias_score") or 0.0)
    confidence_01 = float(bias_profile.get("bias_analysis_confidence") or 0.0)

    # Frontend schema expects percentage-like ints.
    # Preserve tiny but non-zero signals (e.g. 0.001 -> 1 instead of 0).
    bias_score_pct = max(0.0, min(1.0, bias_score_01)) * 100
    confidence_pct = max(0.0, min(1.0, confidence_01)) * 100
    bias_score = 1 if 0.0 < bias_score_pct < 1.0 else int(round(bias_score_pct))
    confidence = 1 if 0.0 < confidence_pct < 1.0 else int(round(confidence_pct))

    return {
        "overallBias": bias_category,
        "biasScore": bias_score,
        "confidence": confidence,
        "sentiment": sentiment_category,
        "indicators": {
            "language": f"Detected {sentiment_category} language tone",
            "sources": "Bias category derived from article-level NLP classifier",
            "framing": f"Overall framing classified as {bias_category}",
        },
    }



def _transform_retrieval_to_frontend_format(article: Article, retrieval_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform raw retrieval output into frontend-expected format.
    
    Converts from:
        {
            "created_article_id": ...,
            "created_claim_ids": [...],
            "matches": [
                {
                    "query_claim": str,
                    "verdict": str,
                    "confidence": int,
                    "matches": [...]
                }
            ]
        }
    
    To:
        {
            "article": {...},
            "trustScore": int,
            "biasAnalysis": {...},
            "keyClaims": [...]
        }
    """
    article_text = cast(str | None, article.text)
    article_content = (article_text or "")[:1800]
    published_at = cast(Any, article.publishedAt)
    
    article_section = {
        "title": article.title or "",
        "url": article.url,
        "content": article_content,
        "source": article.outlet.name if article.outlet else "Unknown",
        "publishedAt": published_at.isoformat() if published_at is not None else "",
    }
    
    # Transform matches into keyClaims
    matches_list = retrieval_result.get("matches", []) or []
    key_claims = []
    
    for idx, match_group in enumerate(matches_list, 1):
        claim_matches = match_group.get("matches", [])
        
        # Transform individual match items into evidence
        evidence = [
            {
                "source": f"Claim #{m['claim_id']}",
                "url": m.get("source_url") or "",
                "excerpt": (m.get("source_excerpt") or m.get("claim_text", ""))[:500],
            }
            for m in claim_matches[:3]  # Limit to top 3 evidence items
        ]
        
        key_claim = {
            "id": str(idx),
            "claim": match_group.get("query_claim", ""),
            "verdict": match_group.get("verdict", "unverified"),
            "confidence": match_group.get("confidence", 0),
            "evidence": evidence,
        }
        key_claims.append(key_claim)
    
    # Calculate overall trustScore from average confidence
    confidences = [m.get("confidence", 0) for m in matches_list]
    trust_score = int(sum(confidences) / len(confidences)) if confidences else 0
    
    bias_analysis = _build_bias_analysis(retrieval_result.get("bias_profile"))
    
    # Extract related articles from retrieval result
    related_articles = retrieval_result.get("related_articles", [])
    
    return {
        "article": article_section,
        "trustScore": trust_score,
        "biasAnalysis": bias_analysis,
        "keyClaims": key_claims,
        "relatedArticles": related_articles,
    }


# Accept both /jobs and /jobs/ to avoid 307 redirects
@router.post("", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
@router.post("/", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_job(job_in: JobCreate, db: Session = Depends(get_db)):
    try:
        requested_job_type = JobType.BACKGROUND.value if job_in.is_background else JobType.USER.value

        # Seen article fast path: reuse most recent job for this URL and skip republishing.
        existing_article = get_article_by_url(db=db, article_url=job_in.article_url)
        if existing_article:
            existing_job = get_latest_job_for_article(
                db=db,
                article_id=cast(int, existing_article.id),
                job_type=requested_job_type,
            )
            if existing_job:
                logger.info(
                    "Seen article detected. Reusing existing job id=%s uid=%s for url=%s",
                    existing_job.id,
                    existing_job.uid,
                    existing_article.url,
                )
                return existing_job

        # Start of the "Unit of Work"
        job_in.news_outlet = get_news_outlet(job_in)
        new_article: Article = create_article(db=db, job_in=job_in)
        new_job: Job = create_job(db=db, job_in=job_in, article_id=cast(int, new_article.id))
        
        # Only publish to Redis if the database commit was successful.
        publish_job(new_job, new_article, job_in)
        
        # All database operations are prepared. Now, commit them as one transaction.
        db.commit() 
        return new_job

    except IntegrityError as e:
        # This can happen if, for example, the article URL already exists (violating a UNIQUE constraint)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Resource already exists. Error: {str(e)}"
        )
    except Exception as e:
        # For any other unexpected error, rollback the entire transaction
        db.rollback()
        logger.error(
            "Failed to submit job for url=%s: %s",
            job_in.article_url,
            e,
            exc_info=(type(e), e, e.__traceback__),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}"
        )


@router.get("/{job_id}", response_model=JobResponse, status_code=status.HTTP_200_OK)
def read_job_status(job_id: int, db: Session = Depends(get_db)):
    job = get_job(db=db, job_id=job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID {job_id} not found."
        )
    
    return job


# result = {
#         "save_data_result" : self.data.payload.save_data_result,
#         "save_job_result": self.data.payload.save_job_result,
#         "matches": self.data.payload.matches,
#         "related_articles": self.data.payload.related_articles
# }

@router.get("/{job_uid}/result", response_model=dict, status_code=status.HTTP_200_OK)
async def get_retrieval_result(job_uid: UUID, timeout: int = Query(30, ge=5, le=60), db: Session = Depends(get_db)):
    """
    Poll Redis for retrieval results matching the job_uid.
    
    Extension calls this endpoint every 5s until it gets a result.
    - Returns 200 with formatted result when retrieval completes
    - Returns 404 if result not found after timeout
    """
    try:
        start_time = asyncio.get_event_loop().time()
        search_for_uid = str(job_uid)
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            result = result_hash_store.get(search_for_uid)
            
            if result:
                # Keep the complete retrieval payload from Redis hash.
                retrieval_result = {
                    "save_data_result": result.get("save_data_result") or {},
                    "save_job_result": result.get("save_job_result") or {},
                    "matches": result.get("matches") or [],
                    "related_articles": result.get("related_articles") or [],
                    "bias_profile": result.get("bias_profile") or {},
                }
                logger.debug(
                    "Retrieved hash payload for job_uid=%s keys=%s matches=%d related_articles=%d",
                    search_for_uid,
                    sorted(list(result.keys())),
                    len(retrieval_result.get("matches", [])),
                    len(retrieval_result.get("related_articles", [])),
                )

                article_id = retrieval_result.get("save_data_result", {}).get("article_entry_id")
                
                if not article_id:
                    raise Exception("Cannot return result! No article_id")
                
                article = db.query(Article).filter(Article.id == article_id).first()
                
                if not article:
                    raise Exception("Cannot return result! No article in database")
                
                formatted_response = _transform_retrieval_to_frontend_format(article, retrieval_result)
                
                return {
                    "ok": True,
                    "job_uid": str(job_uid),
                    "status": JobStatus.COMPLETE,
                    "data": formatted_response
                }
            
            await asyncio.sleep(1)
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Retrieval result not found for job {job_uid} within {timeout}s"
        )
        
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(
            "Failed to retrieve result for job_uid=%s: %s",
            job_uid,
            e,
            exc_info=(type(e), e, e.__traceback__),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving result: {str(e)}"
        )
