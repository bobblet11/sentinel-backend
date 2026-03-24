# for each dump.rdb, create a new folder
# start a new redis server for each
# port 6380 onward

# make sure the merged port is an empty redis instance and is the one running on docker!

import datetime
import hashlib
import json
import time
import re

from typing import Any, Dict, List

import redis
from common.models.api.dtos.job import JobStage, JobStatus, JobType
from common.models.api.redis_models import Message, MessageHeader, MessagePayload, MessageTimestamp, StreamMessage

INPUT_SET_KEY_OPTIONS = ["ingestor:seen.articles"]
INPUT_STREAM_KEY_OPTIONS = ["background:to.be.scraped", "prioritised:to.be.scraped", "background:to.be.nlp", "ingestor:to.be.scraped", "failure:to.be.scraped"]

MERGED_STREAM_KEY="background:to.be.scraped"
MERGED_SET_KEY = "ingestor:seen.articles"
NUMBER_OF_BACKUPS = 8
START_PORT = 6380
ALL_PORTS = [START_PORT + i for i in range(0, NUMBER_OF_BACKUPS)]
MERGED_PORT = 6379
job_start_mono = time.monotonic()

OUTLET_PATTERNS = {
    r"(bbc\.com|bbc\.co\.uk|www\.bbc\.com)": "BBC",
    r"(theguardian\.com|www\.theguardian\.com)": "The Guardian",
    r"(cbc\.ca|www\.cbc\.ca)": "CBC",
    r"(euronews\.com|www\.euronews\.com)": "Euronews",
    r"(abcnews\.go\.com|abcnews\.com)": "ABC",
    r"(cbsnews\.com|www\.cbsnews\.com)": "CBS",
    r"(nbcnews\.com|www\.nbcnews\.com)": "NBC",
    r"(npr\.org|www\.npr\.org)": "NPR",
}

def connect_redis(port: int, host:str="localhost") -> redis.Redis:
    try:
        r = redis.Redis(host=host, port=port, decode_responses=True)
        r.ping()  # quick health check
        print(f"[INFO] Connected to Redis on port {port}")
        return r
    except redis.exceptions.ConnectionError as e:
        print(f"[ERROR] Could not connect to Redis on port {port}: {e}")
        raise RuntimeError(f"Could not connect to Redis on port {port}: {e}")



def match_outlet_name(article_url: str) -> str:
    for pattern, outlet in OUTLET_PATTERNS.items():
        if re.search(pattern, article_url):
            return outlet
    return None


def load_stream_jobs(port, stream_keys: List[str]) -> List[Dict[str, Any]]:
    r = connect_redis(port)
    jobs = []
    for key in stream_keys:
        try:
            entries = r.xrange(key)
        except redis.exceptions.ResponseError as e:
            print(f"[WARN] Could not read stream {key} on port {port}: {e}")
            continue

        for redis_id, fields in entries:
            if "payload" in fields and isinstance(fields["payload"], str):
                try:
                    fields["payload"] = json.loads(fields["payload"])
                except Exception as e:
                    print(f"[❌] Could not parse payload JSON for {redis_id} in {key}: {e}")
                    continue

            jobs.append({
                "stream": key,
                "redis_message_id": redis_id,
                "data": fields
            })
        print(f"[INFO] Loaded {len(entries)} jobs from stream {key} on port {port}")
    return jobs


def sort_jobs_by_id(jobs: List[StreamMessage]) -> List[StreamMessage]:
    def parse_id(redis_id: str) -> tuple[int, int]:
        parts = redis_id.split("-")
        return (int(parts[0]), int(parts[1]))
    return sorted(jobs, key=lambda j: parse_id(j.redis_id), reverse=True)

def sort_jobs_by_created_at(jobs: List[StreamMessage]) -> List[StreamMessage]:
    def parse_created_at(job: StreamMessage):
        try:
            dt = datetime.datetime.fromisoformat(job.data.header.created_at)
            # If it's naive, make it UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except Exception:
            return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
    return sorted(jobs, key=parse_created_at, reverse=True)



def transform_job(raw_msg: Dict[str, Any]) -> StreamMessage:
	"""
	Convert a raw redis stream entry into a typed StreamMessage.
	Missing fields are replaced with None.
	"""
	msg_data = raw_msg.get("data", {})
	payload = msg_data.get("payload", {})
	
	if isinstance(payload, dict) and "payload" in payload and "header" in payload:
		# Legacy format: payload dict contains header + payload
		header = payload.get("header", {})
		inner_payload = payload.get("payload", {})
		stage_timestamps = payload.get("stage_timestamps", [])
	else:
		header = msg_data.get("header", {})
		inner_payload = payload
		stage_timestamps = msg_data.get("stage_timestamps", [])

	article_url = (
		inner_payload.get("article_url")
		or inner_payload.get("url")
		or (inner_payload.get("data", {}) or {}).get("url")
	)

	created_at_raw = header.get("created_at") or header.get("timestamp")
	if not article_url:
		print(f"[❌] Job missing article_url (stream={raw_msg.get('stream')}, redis_id={raw_msg.get('redis_message_id')})")
		raise RuntimeError(f"Malformed job: missing article_url\n{json.dumps(raw_msg, indent=2)}")
		return None

	if created_at_raw:
		try:
			dt = datetime.datetime.fromisoformat(created_at_raw)
			if dt.tzinfo is None:
				dt = dt.replace(tzinfo=datetime.timezone.utc)
			created_at = dt.isoformat()
		except Exception:
			print(f"[WARN] Invalid created_at format for {article_url}, falling back to now()")
			created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
	else:
		created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()


	uid=hashlib.md5(article_url.encode()).hexdigest()[:36]
 
	news_outlet = match_outlet_name(article_url)
	if not news_outlet:
		print(f"[❌] No outlet match for {article_url} (stream={raw_msg.get('stream')}, redis_id={raw_msg.get('redis_message_id')})")
		# raise RuntimeError(f"Malformed job: missing news outlet\n{json.dumps(raw_msg, indent=2)}")
		return None


	# print(f"[✅] Transforming job: url={article_url}, outlet={news_outlet}, redis_id={raw_msg.get('redis_message_id')}")
	created_at_raw = msg_data.get("header", {}).get("created_at")
	
	# --- Header --- (not redis id)
	header = MessageHeader(
		#id is db id, will be None for background jobs
		id=None,
		uid=uid,
		type=JobType.BACKGROUND.value,
		status=JobStatus.PENDING.value,
		created_at=created_at
	)

	# --- Payload ---
	payload = MessagePayload(
		article_url=article_url,
		news_outlet=news_outlet,
  
		# all of these fields need to be validated in INGESTOR
		title=msg_data.get("payload", {}).get("title"),
		publish_date=msg_data.get("payload", {}).get("publish_date"),
		author=msg_data.get("payload", {}).get("author"),
		summary=msg_data.get("payload", {}).get("summary"),
  
		raw_html=None,
		parsed_text=None,
		sentences= [],
		claims_in_article=[],
		entities_in_article=[],
		bias_profile=None,
		save_data_result=None,
		save_job_result=None,
		matches=None,
		related_articles=None,
	)

	# --- Stage timestamps ---
	stage_timestamps: List[MessageTimestamp] = []
	for ts in msg_data.get("stage_timestamps", []):
		stage_timestamps.append(
			MessageTimestamp(
				job_uid=uid,
				stage_name=ts.get("stage_name"),
				wall_time=ts.get("wall_time"),
				offset_s=ts.get("offset_s"),
			)
		)
  
	if not stage_timestamps:
		# print(f"[INFO] No stage_timestamps for {article_url}, adding INGESTED timestamp")
		wall = datetime.datetime.now(datetime.timezone.utc)
		offset = time.monotonic() - job_start_mono

		timestamp_row = MessageTimestamp(
			job_uid = uid,
			stage_name = JobStage.INGESTED.value,
			wall_time = wall.isoformat(),
			offset_s = offset
		)
		stage_timestamps.append(timestamp_row)

	# --- Message ---
	message = Message(
		header=header,
		payload=payload,
		stage_timestamps=stage_timestamps,
	)

	# --- StreamMessage ---
	return StreamMessage(
		stream=raw_msg.get("stream"),
		redis_id=raw_msg.get("redis_message_id"),
		data=message,
		priority=raw_msg.get("priority", 0),  # default to 0 if missing
	)

print(f"[INFO] trying to connect to merged")
merged = connect_redis(host="redis", port=MERGED_PORT)
merged.delete(MERGED_STREAM_KEY)
merged.delete(MERGED_SET_KEY)
print(f"[INFO] connected to merged")

total_dupe_count=0
total_fail_count=0

article_urls_seen = set()
all_jobs: List[StreamMessage] = []

for port in ALL_PORTS:  # ports for each backup instance
	dupe_count=0
	fail_count=0
	untransformed_jobs=load_stream_jobs(port, INPUT_STREAM_KEY_OPTIONS)
	for raw in untransformed_jobs:
		job = transform_job(raw)
		if job and job.data.payload.article_url not in article_urls_seen:
			article_urls_seen.add(job.data.payload.article_url)
			all_jobs.append(job)
			# print(f"[INFO] Added job for {job.data.payload.article_url} from port {port}")
		else:
			if job:
				# print(f"[INFO] Duplicate skipped: {job.data.payload.article_url} from port {port}")
				dupe_count+=1
			else:
				# print(f"[WARN] Skipped malformed job from port {port}")
				fail_count+=1
    
	print(f"\n\n========== PORT {port} SUMMARY ==========")
	print(f"Total jobs duplicates: {dupe_count}")
	print(f"Total jobs malformed: {fail_count}")
	print( "=========================================\n\n")

	total_dupe_count+=dupe_count
	total_fail_count+=fail_count

 
all_jobs = sort_jobs_by_created_at(all_jobs)

assert len(all_jobs) == len(article_urls_seen)
print(f"[INFO] Writing {len(all_jobs)} jobs and {len(article_urls_seen)} URLs to merged Redis...")
for job in all_jobs:
    merged.xadd(MERGED_STREAM_KEY, {"payload": json.dumps(job.data.model_dump())})
print(f"[INFO] Stream write complete")
merged.sadd(MERGED_SET_KEY, *article_urls_seen or [])
print(f"[INFO] Set write complete")



print("[INFO] Running post-merge validation...")
set_len = merged.scard(MERGED_SET_KEY)
stream_len = merged.xlen(MERGED_STREAM_KEY)
print(f"[INFO] Set contains {set_len} entries, expected {len(article_urls_seen)}")
print(f"[INFO] Stream contains {stream_len} entries, expected {len(all_jobs)}")

# Check set entries count matches
if set_len != len(article_urls_seen):
    raise AssertionError(f"Set length mismatch: {set_len} vs {len(article_urls_seen)}")

# Check stream entries count matches
if stream_len != len(all_jobs):
    raise AssertionError(f"Stream length mismatch: {stream_len} vs {len(all_jobs)}")

# Check every job URL is in the set
for job in all_jobs:
	url = job.data.payload.article_url
	if not merged.sismember(MERGED_SET_KEY, url):
		print(f"[ERROR] URL {url} missing from {MERGED_SET_KEY}")
		raise AssertionError(f"URL {url} missing from {MERGED_SET_KEY}")


assert merged.scard(MERGED_SET_KEY) == len(article_urls_seen)
assert merged.xlen(MERGED_STREAM_KEY) == len(all_jobs)



print("========== MERGE SUMMARY ==========")
print(f"Total jobs processed: {len(all_jobs)}")
print(f"Total jobs duplicates: {total_dupe_count}")
print(f"Total jobs malformed: {total_fail_count}")
print(f"Unique URLs added:   {len(article_urls_seen)}")
print(f"Stream length:       {merged.xlen(MERGED_STREAM_KEY)}")
print(f"Set length:          {merged.scard(MERGED_SET_KEY)}")
print("===================================")
