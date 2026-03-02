"""Add isbn column to books table

Revision ID: 002
Revises: 001
Create Date: 2026-03-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("books", sa.Column("isbn", sa.String(20), nullable=True))
    op.create_index("ix_books_isbn", "books", ["isbn"])


def downgrade() -> None:
    op.drop_index("ix_books_isbn", table_name="books")
    op.drop_column("books", "isbn")
