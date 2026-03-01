from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuthorSummary(BaseModel):
    id: UUID
    ol_author_key: str
    name: str
    birth_date: str | None = None

    model_config = {"from_attributes": True}


class BookSummary(BaseModel):
    id: UUID
    ol_work_key: str
    title: str
    authors: list[str]
    first_publish_year: int | None = None
    cover_url: str | None = None
    subjects: list[str]

    model_config = {"from_attributes": True}


class BookDetail(BaseModel):
    id: UUID
    ol_work_key: str
    title: str
    authors: list[AuthorSummary]
    first_publish_year: int | None = None
    cover_url: str | None = None
    description: str | None = None
    subjects: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
