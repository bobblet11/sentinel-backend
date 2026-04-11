from pydantic import BaseModel
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from enum import StrEnum
class JobStatus(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"
    
class JobType(StrEnum):
    BACKGROUND = "background"
    USER = "user"
    
class JobStage(StrEnum):
    INGESTED = "-- INGESTED --"
    
    WEB_SCRAPE_START = "-- WEB SCRAPER START --"
    FETCHED_IN = "starting fetch HTML"
    FETCHED_OUT = "ending fetch HTML"
    PARSED_IN = "starting parsing HTML"
    PARSED_OUT = "ending parsing HTML"
    WEB_SCRAPE_END = "-- WEB SCRAPER END --"
    
    
    NLP_START = "-- NLP START --"
    
    PREPROCESS_IN = "started preprocessing text (1)"
    PREPROCESS_OUT = "ended preprocessing text (1)"
    
    NER_IN = "started NER on text (2)"
    NER_OUT = "ended NER on text (2)"
    
    SENT_EXTRACTION_IN = "started sentence extraction (3)"
    SENT_EXTRACTION_OUT = "ended sentence extraction (3)"
    
    DECONTEXT_IN = "started decontextualisation (4)"
    DECONTEXT_OUT = "ended decontextualisation (4)"
    
    CHECK_WORTHY_IN = "started check worthy (5)"
    CHECK_WORTHY_OUT = "ended check worthy (5)"
    
    CHECK_WORTHY_ENTITY_MAPPING_IN = "started entity mapping (5.5)"
    CHECK_WORTHY_ENTITY_MAPPING_OUT = "ended entity mapping (5.5)"
    
    SENTENCE_EMBED_IN = "started creating vector embedding (6)"
    SENTENCE_EMBED_OUT = "ended creating vector embedding (6)"
    
    CONVERT_TO_CLAIM_IN = "started Sentence -> Claim Conversion (7)"
    CONVERT_TO_CLAIM_OUT = "ended Sentence -> Claim Conversion (7)"
    
    BIAS_ANAL_IN = "started Bias Analysis (8)"
    BIAS_ANAL_OUT = "ended Bias Analysis (8)"
    
    NLP_END = "-- NLP END --"
    
    RETRIEVAL_START = "-- RETRIEVAL START --"
    
    SAVE_DATA_IN = "started saving data into postgres"
    SAVE_DATA_OUT = "ended saving data into postgres"
    
    RETRIEVE_EVIDENCE_IN = "started retrieving support/dispute claims from database"
    RETRIEVE_EVIDENCE_OUT = "ended retrieving support/dispute claims from database"
    
    UPDATE_JOB_IN = "started updating job status into postgres"
    UPDATE_JOB_OUT = "ended updating job status into postgres"
    
    RETRIEVAL_END = "-- RETRIEVAL END --"
    

    
class JobCreate(BaseModel):
    article_url: str
    article_html: str
class JobResponse(BaseModel):
    id: int
    status: str
    type: str
    created_at: datetime
