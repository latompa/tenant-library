"""Fair per-tenant task scheduler using Redis queues.

Instead of dispatching Celery tasks directly, tasks are enqueued into
per-tenant Redis lists.  A periodic scheduler (via Celery Beat) pops one
task from each tenant in round-robin fashion and pushes them to the real
Celery queue, preventing any single tenant from starving others.

Redis keys:
  fairq:tenant:{tenant_id}  — per-tenant task list (RPUSH / LPOP)
  fairq:tenants              — set of tenant IDs with pending work
  fairq:dispatch_lock        — short-lived lock to prevent concurrent dispatches
"""

import json
import logging

import redis as sync_redis

from app.config import settings

logger = logging.getLogger(__name__)

TENANT_QUEUE_PREFIX = "fairq:tenant:"
TENANTS_SET_KEY = "fairq:tenants"
DISPATCH_LOCK_KEY = "fairq:dispatch_lock"
CELERY_QUEUE_KEY = "celery"
MAX_CELERY_QUEUE_DEPTH = 2


def _get_sync_redis():
    return sync_redis.from_url(settings.REDIS_URL, decode_responses=True)


def enqueue_task(tenant_id: str, task_name: str, kwargs: dict) -> None:
    """Enqueue a task into the fair per-tenant queue (sync, for Celery tasks)."""
    r = _get_sync_redis()
    try:
        payload = json.dumps({"task_name": task_name, "kwargs": kwargs})
        pipe = r.pipeline()
        pipe.rpush(f"{TENANT_QUEUE_PREFIX}{tenant_id}", payload)
        pipe.sadd(TENANTS_SET_KEY, tenant_id)
        pipe.execute()
    finally:
        r.close()


async def enqueue_task_async(tenant_id: str, task_name: str, kwargs: dict) -> None:
    """Enqueue a task into the fair per-tenant queue (async, for FastAPI handlers)."""
    import redis.asyncio as aioredis

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        payload = json.dumps({"task_name": task_name, "kwargs": kwargs})
        pipe = r.pipeline()
        pipe.rpush(f"{TENANT_QUEUE_PREFIX}{tenant_id}", payload)
        pipe.sadd(TENANTS_SET_KEY, tenant_id)
        await pipe.execute()
    finally:
        await r.aclose()


def dispatch_fair_batch() -> int:
    """Pop one task per tenant round-robin and send to Celery.

    Returns the number of tasks dispatched.
    """
    from app.tasks.celery_app import celery_app

    r = _get_sync_redis()
    dispatched = 0
    try:
        # Non-blocking lock — skip if another dispatch is running
        if not r.set(DISPATCH_LOCK_KEY, "1", nx=True, ex=10):
            logger.debug("Fair dispatch skipped — lock held")
            return 0

        try:
            # Check Celery queue depth — keep it shallow for fairness
            queue_depth = r.llen(CELERY_QUEUE_KEY)
            available_slots = MAX_CELERY_QUEUE_DEPTH - queue_depth
            if available_slots <= 0:
                logger.debug("Celery queue full (%d), skipping dispatch", queue_depth)
                return 0

            tenant_ids = r.smembers(TENANTS_SET_KEY)
            if not tenant_ids:
                return 0

            for tenant_id in sorted(tenant_ids):  # sorted for deterministic ordering
                if dispatched >= available_slots:
                    break

                raw = r.lpop(f"{TENANT_QUEUE_PREFIX}{tenant_id}")
                if raw is None:
                    # Queue empty — remove from set
                    r.srem(TENANTS_SET_KEY, tenant_id)
                    continue

                payload = json.loads(raw)
                task_name = payload["task_name"]
                kwargs = payload["kwargs"]

                celery_app.send_task(task_name, kwargs=kwargs)
                dispatched += 1
                logger.info("Dispatched %s for tenant %s", task_name, tenant_id)

                # Check if tenant still has pending tasks
                remaining = r.llen(f"{TENANT_QUEUE_PREFIX}{tenant_id}")
                if remaining == 0:
                    r.srem(TENANTS_SET_KEY, tenant_id)

        finally:
            r.delete(DISPATCH_LOCK_KEY)

    finally:
        r.close()

    return dispatched
