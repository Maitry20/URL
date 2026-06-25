import redis
from config import settings

# Create a Redis client with a short timeout to prevent blocking during network delays
try:
    redis_client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD or None,
        decode_responses=True,  # Automatically decodes bytes to strings
        socket_connect_timeout=2.0,
        socket_timeout=2.0
    )
except Exception as e:
    print(f"Redis initialization warning: {e}")
    redis_client = None

def get_cached_url(code: str) -> str | None:
    """
    Retrieves the original URL from Redis cache using the short code.
    Returns None if cache miss or Redis is unavailable.
    """
    if redis_client is None:
        return None
    try:
        return redis_client.get(f"url:{code}")
    except Exception as e:
        print(f"Redis cache read error for code '{code}': {e}")
        return None

def set_cached_url(code: str, original_url: str, ttl: int = 3600) -> bool:
    """
    Stores the short code and original URL mapping in Redis with a TTL (default 1 hour).
    Returns True if successful, False otherwise.
    """
    if redis_client is None:
        return False
    try:
        # setex sets value with an expiration time in seconds
        redis_client.setex(f"url:{code}", ttl, original_url)
        return True
    except Exception as e:
        print(f"Redis cache write error for code '{code}': {e}")
        return False

def delete_cached_url(code: str) -> bool:
    """
    Removes a short code mapping from Redis cache.
    """
    if redis_client is None:
        return False
    try:
        redis_client.delete(f"url:{code}")
        return True
    except Exception as e:
        print(f"Redis cache delete error for code '{code}': {e}")
        return False
