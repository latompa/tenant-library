import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ReadingList(Base):
    __tablename__ = "reading_lists"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email_hash", name="uq_reading_lists_tenant_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    patron_name_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    email_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    patron_name_masked: Mapped[str] = mapped_column(String(255), nullable=False)
    email_masked: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)

    items = relationship("ReadingListItem", lazy="selectin", cascade="all, delete-orphan")


class ReadingListItem(Base):
    __tablename__ = "reading_list_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reading_list_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reading_lists.id", ondelete="CASCADE"), nullable=False, index=True)
    ol_work_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    isbn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    book_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("books.id"), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
