import asyncio
import logging
from functools import wraps

logger = logging.getLogger(__name__)


async def retry_async(func, *args, max_retries: int = 5, delay: float = 2.0, backoff: float = 2.0, **kwargs):
    if max_retries <= 0:
        raise ValueError("max_retries must be greater than 0")
    last_exc = None
    current_delay = delay
    for attempt in range(1, max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                logger.warning(f"{func.__name__} attempt {attempt}/{max_retries} failed: {e}, retrying in {current_delay}s")
                await asyncio.sleep(current_delay)
                current_delay *= backoff
    logger.error(f"{func.__name__} failed after {max_retries} attempts: {last_exc}")
    raise last_exc


def retryable(max_retries: int = 5, delay: float = 2.0, backoff: float = 2.0):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_async(func, *args, max_retries=max_retries, delay=delay, backoff=backoff, **kwargs)
        return wrapper
    return decorator
