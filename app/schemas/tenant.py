"""Tenant schemas."""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class TenantCreate(BaseModel):
    name: str
    slug: str

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", v):
            raise ValueError("Slug must be lowercase alphanumeric with hyphens")
        return v


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime

    model_config = {"from_attributes": True}
