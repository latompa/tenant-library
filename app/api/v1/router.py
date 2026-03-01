from fastapi import APIRouter

from app.api.v1.activity_log import router as activity_log_router
from app.api.v1.books import router as books_router
from app.api.v1.ingestion import router as ingestion_router

v1_router = APIRouter()

tenant_prefix = "/tenants/{tenant_slug}"

v1_router.include_router(books_router, prefix=tenant_prefix)
v1_router.include_router(ingestion_router, prefix=tenant_prefix)
v1_router.include_router(activity_log_router, prefix=tenant_prefix)
