import hashlib
import urllib.parse


def url_key(u: str) -> str:
    """Generate deterministic cache key for URL"""
    h = hashlib.sha256(u.encode("utf-8")).hexdigest()
    return f"analysis:{h}"


def httpx_encode(u: str) -> str:
    """URL encode helper to avoid importing heavy libs"""
    return urllib.parse.quote_plus(u)
