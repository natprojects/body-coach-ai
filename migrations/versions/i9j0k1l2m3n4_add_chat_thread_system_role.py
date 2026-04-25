"""add system_role to chat_threads

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Branch Labels: None
Depends On: None
"""
from alembic import op
import sqlalchemy as sa

revision = 'i9j0k1l2m3n4'
down_revision = 'h8i9j0k1l2m3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('chat_threads', schema=None) as batch_op:
        batch_op.add_column(sa.Column('system_role', sa.String(40), nullable=True))


def downgrade():
    with op.batch_alter_table('chat_threads', schema=None) as batch_op:
        batch_op.drop_column('system_role')
