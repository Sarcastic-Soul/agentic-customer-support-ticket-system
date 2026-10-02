"""add agent_steps.agent for specialist lanes

Revision ID: 3b7d2c9a41f0
Revises: 1e60bc305630
Create Date: 2026-10-01 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3b7d2c9a41f0'
down_revision: Union[str, Sequence[str], None] = '1e60bc305630'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('agent_steps', sa.Column('agent', sa.String(), nullable=True))
    # the approval queue lists refunds by status
    op.create_index('ix_refunds_status', 'refunds', ['status'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_refunds_status', table_name='refunds')
    op.drop_column('agent_steps', 'agent')
