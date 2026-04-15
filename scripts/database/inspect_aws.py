#!/usr/bin/env python3
import redis
from dotenv import load_dotenv
# Load environment
load_dotenv(dotenv_path="configs/aws/.env")

from common.redis_client.connection import redis_connection

def bar(value, max_value, length=20):
    """Simple ASCII bar chart."""
    if max_value == 0:
        return "[....................]"
    filled = int((value / max_value) * length)
    return "[" + "*" * filled + "." * (length - filled) + "]"

def inspect_redis():
    r = redis_connection.get_client()

    stream_stats, set_stats, hash_stats = {}, {}, {}
    cursor = 0
    while True:
        cursor, keys = r.scan(cursor=cursor, count=500)
        for key in keys:
            key_type = r.type(key)
            key_name = key.decode() if isinstance(key, bytes) else key
            if key_type == "stream":
                stream_stats[key_name] = r.xlen(key)
            elif key_type == "set":
                set_stats[key_name] = r.scard(key)
            elif key_type == "hash":
                hash_stats[key_name] = r.hlen(key)
        if cursor == 0:
            break

    # Service-level metrics
    failures = {
        "scraper": stream_stats.get("failure:to.be.scraped", 0),
        "nlp": stream_stats.get("failure:to.be.nlp", 0),
        "retrieval": stream_stats.get("failure:to.be.retrieval", 0),
    }
    waiting = {
        "scraper": stream_stats.get("background:to.be.nlp", 0) + stream_stats.get("user:to.be.nlp", 0),
        "nlp": stream_stats.get("background:to.be.retrieval", 0) + stream_stats.get("user:to.be.retrieval", 0),
        "retrieval": stream_stats.get("retrieval:uid.store", 0),
    }
    completed = set_stats.get("retrieval:uid.store", 0)
    total_ingested = stream_stats.get("background:to.be.scraped", 0) + stream_stats.get("user:to.be.scraped", 0)

    print("\n====================================")
    print("        REDIS PIPELINE DASHBOARD")
    print("====================================\n")

    print(">>> SERVICE LEVEL")
    for service in ["scraper", "nlp", "retrieval"]:
        w = waiting.get(service, 0)
        f = failures.get(service, 0)
        # Success rate based on completed vs total ingested (retry-safe)
        total = total_ingested if total_ingested > 0 else 1
        success_rate = (completed / total) * 100 if service == "retrieval" else None
        print(f"[{service.upper()}]")
        print(f"  Waiting : {w}")
        print(f"  Failed  : {f} (events, may include retries)")
        if success_rate is not None:
            print(f"  Success : {success_rate:.1f}% (completed vs ingested)")
        print()

    print(">>> PIPELINE FLOW")
    print(f"[ background:to.be.scraped ] ({stream_stats.get('background:to.be.scraped',0)})")
    print("            |")
    print("            v")
    print(f"[ background:to.be.nlp ] ({stream_stats.get('background:to.be.nlp',0)}) ----> failure:to.be.scraped ({failures['scraper']})")
    print("            |")
    print("            v")
    print(f"[ background:to.be.retrieval ] ({stream_stats.get('background:to.be.retrieval',0)}) ----> failure:to.be.nlp ({failures['nlp']})")
    print("            |")
    print("            v")
    print(f"[ retrieval:uid.store ] ({completed} completed) ----> failure:to.be.retrieval ({failures['retrieval']})")

    print("\n>>> CONSUMER HEALTH")
    for stream in stream_stats.keys():
        try:
            groups = r.xinfo_groups(stream)
            for group in groups:
                group_name = group["name"]

                # Load per-consumer ack counters for this stream/group
                ack_key = f"stream:{stream}:group:{group_name}:acks"
                ack_stats = r.hgetall(ack_key)  # {b'consumer_name': b'count', ...}

                consumers = r.xinfo_consumers(stream, group_name)
                max_pending = max([c["pending"] for c in consumers]) if consumers else 0

                print(f"\nStream: {stream} | Group: {group_name}")
                for consumer in consumers:
                    cname = consumer["name"]
                    pending_count = consumer["pending"]

                    # Redis returns hash keys/vals as bytes if decode_responses=False
                    raw_acked = ack_stats.get(
                        cname if isinstance(next(iter(ack_stats.keys()), None), str) else cname.encode()
                    )
                    acked = int(raw_acked) if raw_acked is not None else 0

                    print(
                        f"  {cname:<20} {bar(pending_count, max_pending)} "
                        f"{pending_count} pending | {acked} acked"
                    )
        except redis.exceptions.ResponseError:
            # Not a stream with groups, or no groups defined
            pass

    print("\n====================================\n")

if __name__ == "__main__":
    inspect_redis()