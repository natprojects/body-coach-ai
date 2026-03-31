"""add app_language to users

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('app_language', sa.String(10), nullable=True, server_default='en'))


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('app_language')
