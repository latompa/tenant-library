"""Per-tenant API rate limiting middleware using Redis fixed-window counters."""

import logging
import re
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

# Matches tenant-scoped routes only (requires path segment after the slug)
_TENANT_RE = re.compile(r"^/api/v1/tenants/([^/]+)/.+$")


class TenantRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        match = _TENANT_RE.match(request.url.path)
        if not match:
            return await call_next(request)

        tenant_slug = match.group(1)
        limit = settings.RATE_LIMIT_PER_MINUTE
        now_minute = int(time.time()) // 60
        redis_key = f"ratelimit:{tenant_slug}:{now_minute}"
        window_reset = (now_minute + 1) * 60  # epoch second when window resets

        try:
            import redis.asyncio as aioredis

            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            try:
                pipe = r.pipeline()
                pipe.incr(redis_key)
                pipe.expire(redis_key, 60, nx=True)
                results = await pipe.execute()
                current_count = results[0]
            finally:
                await r.aclose()
        except Exception:
            logger.warning("Redis unavailable for rate limiting — allowing request", exc_info=True)
            return await call_next(request)

        remaining = max(0, limit - current_count)

        if current_count > limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={
                    "Retry-After": str(window_reset - int(time.time())),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(window_reset),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(window_reset)
        return response
