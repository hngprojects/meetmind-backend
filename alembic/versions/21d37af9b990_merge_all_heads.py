"""merge all heads

Revision ID: 21d37af9b990
Revises: 62e9bff51378, 949a555f7d56
Create Date: 2026-05-14 00:00:11.370269

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '21d37af9b990'
down_revision: Union[str, None] = ('62e9bff51378', '949a555f7d56')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
