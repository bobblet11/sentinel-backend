# async HTTP helper with timeout and simple retry
import httpx
from config import HTTP_TIMEOUT


async def fetch_json(
    url: str,
    method: str = "GET",
    json: dict | None = None,
    timeout: float | None = None,
):
    timeout = timeout or HTTP_TIMEOUT
    async with httpx.AsyncClient(timeout=timeout) as client:
        if method.upper() == "GET":
            r = await client.get(url)
        else:
            r = await client.post(url, json=json)
        r.raise_for_status()
        return r.json()
