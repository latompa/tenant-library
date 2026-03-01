from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class IngestionJobResponse(BaseModel):
    job_id: UUID
    status: str
    message: str


class IngestionJobDetail(BaseModel):
    id: UUID
    query_type: str
    query_value: str
    limit: int
    status: str
    progress: dict | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
