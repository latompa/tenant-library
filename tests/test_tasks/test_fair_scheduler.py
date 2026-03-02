"""Tests for fair per-tenant task scheduler."""

import json
import uuid
from unittest.mock import patch

import pytest
import redis as sync_redis

from app.config import settings
from app.tasks.fair_scheduler import (
    TENANT_QUEUE_PREFIX,
    TENANTS_SET_KEY,
    dispatch_fair_batch,
    enqueue_task,
)


@pytest.fixture
def redis_client():
    r = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
    yield r
    r.close()


@pytest.fixture(autouse=True)
def _clean_fair_keys(redis_client):
    """Remove all fair-queue keys before and after each test."""
    def cleanup():
        keys = redis_client.keys("fairq:*")
        if keys:
            redis_client.delete(*keys)

    cleanup()
    yield
    cleanup()


def test_enqueue_creates_list_and_set(redis_client):
    """enqueue_task should RPUSH to tenant list and SADD to tenants set."""
    tid = str(uuid.uuid4())
    enqueue_task(tid, "my.task", {"key": "val"})

    assert redis_client.sismember(TENANTS_SET_KEY, tid)
    assert redis_client.llen(f"{TENANT_QUEUE_PREFIX}{tid}") == 1

    payload = json.loads(redis_client.lindex(f"{TENANT_QUEUE_PREFIX}{tid}", 0))
    assert payload["task_name"] == "my.task"
    assert payload["kwargs"] == {"key": "val"}


def test_enqueue_multiple(redis_client):
    """Multiple enqueues for the same tenant should grow the list."""
    tid = str(uuid.uuid4())
    enqueue_task(tid, "task.a", {})
    enqueue_task(tid, "task.b", {})
    enqueue_task(tid, "task.c", {})

    assert redis_client.llen(f"{TENANT_QUEUE_PREFIX}{tid}") == 3


@patch("app.tasks.celery_app.celery_app.send_task")
@patch("app.tasks.fair_scheduler.CELERY_QUEUE_KEY", "test_celery_depth")
def test_dispatch_round_robin(mock_send, redis_client):
    """dispatch_fair_batch should pop one task per tenant, not all from one."""
    tid_a = "aaaaaaaa-0000-0000-0000-000000000001"
    tid_b = "bbbbbbbb-0000-0000-0000-000000000002"

    # 3 tasks for A, 1 for B
    for i in range(3):
        enqueue_task(tid_a, f"task_a_{i}", {"i": i})
    enqueue_task(tid_b, "task_b_0", {"i": 0})

    dispatched = dispatch_fair_batch()
    assert dispatched == 2  # one from each tenant
    assert mock_send.call_count == 2

    # A should still have 2 remaining
    assert redis_client.llen(f"{TENANT_QUEUE_PREFIX}{tid_a}") == 2
    # B should be empty
    assert redis_client.llen(f"{TENANT_QUEUE_PREFIX}{tid_b}") == 0
    assert not redis_client.sismember(TENANTS_SET_KEY, tid_b)


@patch("app.tasks.celery_app.celery_app.send_task")
@patch("app.tasks.fair_scheduler.CELERY_QUEUE_KEY", "test_celery_depth")
def test_dispatch_respects_queue_depth(mock_send, redis_client):
    """If Celery queue is at capacity, dispatch should skip."""
    tid = str(uuid.uuid4())
    enqueue_task(tid, "my.task", {})

    # Push to a test-only key (not the real broker queue) to simulate depth
    redis_client.rpush("test_celery_depth", "x", "x", "x")
    try:
        dispatched = dispatch_fair_batch()
        assert dispatched == 0
        assert mock_send.call_count == 0
        # Task should still be in the fair queue
        assert redis_client.llen(f"{TENANT_QUEUE_PREFIX}{tid}") == 1
    finally:
        redis_client.delete("test_celery_depth")


@patch("app.tasks.celery_app.celery_app.send_task")
@patch("app.tasks.fair_scheduler.CELERY_QUEUE_KEY", "test_celery_depth")
def test_dispatch_cleans_empty_tenants(mock_send, redis_client):
    """After draining a tenant's queue, it should be removed from the set."""
    tid = str(uuid.uuid4())
    enqueue_task(tid, "my.task", {})

    dispatch_fair_batch()

    assert not redis_client.sismember(TENANTS_SET_KEY, tid)
    assert redis_client.llen(f"{TENANT_QUEUE_PREFIX}{tid}") == 0


@patch("app.tasks.fair_scheduler.CELERY_QUEUE_KEY", "test_celery_depth")
def test_dispatch_noop_when_empty(redis_client):
    """dispatch_fair_batch on empty queues should return 0."""
    assert dispatch_fair_batch() == 0


@pytest.mark.asyncio
async def test_enqueue_task_async():
    """Async variant should enqueue identically to the sync version."""
    import redis.asyncio as aioredis

    from app.tasks.fair_scheduler import enqueue_task_async

    tid = str(uuid.uuid4())
    await enqueue_task_async(tid, "async.task", {"a": 1})

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        assert await r.sismember(TENANTS_SET_KEY, tid)
        assert await r.llen(f"{TENANT_QUEUE_PREFIX}{tid}") == 1
    finally:
        await r.aclose()
