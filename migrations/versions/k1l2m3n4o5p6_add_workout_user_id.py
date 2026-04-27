"""add user_id to workouts for mini-session ownership

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
"""
from alembic import op
import sqlalchemy as sa

revision = 'k1l2m3n4o5p6'
down_revision = 'j0k1l2m3n4o5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('workouts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_workouts_user_id', 'users', ['user_id'], ['id'])


def downgrade():
    with op.batch_alter_table('workouts', schema=None) as batch_op:
        batch_op.drop_column('user_id')
