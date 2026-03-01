from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant
from app.clients.openlibrary import OpenLibraryClient
from app.database import get_session
from app.models.tenant import Tenant
from app.schemas.ingestion import IngestionRequest, IngestionResponse
from app.services.ingestion_service import IngestionService

router = APIRouter(tags=["ingestion"])


@router.post("/ingestion", response_model=IngestionResponse)
async def trigger_ingestion(
    body: IngestionRequest,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    """Trigger catalog ingestion from Open Library by author or subject.

    Currently runs synchronously. Will be moved to Celery background task.
    """
    ol_client = OpenLibraryClient()
    try:
        service = IngestionService(session, ol_client)
        log = await service.ingest(
            tenant_id=tenant.id,
            query_type=body.query_type,
            query_value=body.query_value,
            limit=body.limit,
        )
        return IngestionResponse(
            message=f"Ingestion {log.status} for {body.query_type} '{body.query_value}'",
            log_id=log.id,
            query_type=log.query_type,
            query_value=log.query_value,
            works_fetched=log.works_fetched,
            works_stored=log.works_stored,
            works_failed=log.works_failed,
            status=log.status,
        )
    finally:
        await ol_client.close()
