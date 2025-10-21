import redis.asyncio as redis   
import json
from typing import Any, Optional
from config import REDIS_URL

_redis = None

async def get_redis():
    global _redis
    if _redis is None:
        _redis = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis

async def get_cache(key: str) -> Optional[Any]:
    r = await get_redis()
    raw = await r.get(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return raw

async def set_cache(key: str, value: Any, ttl: int = 3600) -> None:
    r = await get_redis()
    await r.set(key, json.dumps(value), ex=ttl)
