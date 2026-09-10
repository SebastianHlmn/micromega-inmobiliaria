"""initial schema

Revision ID: 0001
Revises:
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # La V0 crea las tablas automáticamente al iniciar. Esta migración base
    # queda intencionalmente vacía; al consolidar el modelo se generará una
    # migración formal con `alembic revision --autogenerate`.
    pass


def downgrade() -> None:
    pass
