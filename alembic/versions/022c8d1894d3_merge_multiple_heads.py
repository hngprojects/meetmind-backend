"""merge multiple heads

Revision ID: 022c8d1894d3
Revises: 64a8c4b4d071, 864df66fbeb7, 8d114ef61fcc, 96700cb85b61
Create Date: 2026-05-07 05:07:45.536924

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '022c8d1894d3'
down_revision: Union[str, None] = ('64a8c4b4d071', '864df66fbeb7', '8d114ef61fcc', '96700cb85b61')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
