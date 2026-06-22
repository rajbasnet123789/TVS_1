from fastapi import Request
from slowapi import Limiter


def _key_func(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    if client:
        return client.host
    return "127.0.0.1"


limiter = Limiter(key_func=_key_func)
