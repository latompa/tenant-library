from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class BookReference(BaseModel):
    ol_work_key: str | None = None
    isbn: str | None = None

    @model_validator(mode="after")
    def at_least_one_identifier(self):
        if not self.ol_work_key and not self.isbn:
            raise ValueError("At least one of ol_work_key or isbn must be provided")
        return self


class ReadingListSubmission(BaseModel):
    patron_name: str = Field(min_length=1, max_length=255)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    books: list[BookReference] = Field(min_length=1)


class ResolvedBook(BaseModel):
    ol_work_key: str
    title: str
    found_in_catalog: bool


class UnresolvedBook(BaseModel):
    ol_work_key: str | None = None
    isbn: str | None = None
    reason: str


class ReadingListResponse(BaseModel):
    reading_list_id: UUID
    is_update: bool
    patron_name_masked: str
    email_masked: str
    resolved_books: list[ResolvedBook]
    unresolved_books: list[UnresolvedBook]


class ReadingListItemOut(BaseModel):
    ol_work_key: str | None
    isbn: str | None
    resolved: bool

    model_config = {"from_attributes": True}


class ReadingListOut(BaseModel):
    id: UUID
    patron_name_masked: str
    email_masked: str
    items: list[ReadingListItemOut]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
