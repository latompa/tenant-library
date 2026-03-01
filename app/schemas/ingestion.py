from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class IngestionRequest(BaseModel):
    query_type: Literal["author", "subject"]
    query_value: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=50, ge=1, le=500)


class IngestionResponse(BaseModel):
    message: str
    log_id: UUID
    query_type: str
    query_value: str
    works_fetched: int
    works_stored: int
    works_failed: int
    status: str


class IngestionLogEntry(BaseModel):
    id: UUID
    query_type: str
    query_value: str
    works_fetched: int
    works_stored: int
    works_failed: int
    status: str
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
