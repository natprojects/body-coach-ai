"""add last_exercise_id to workout_sessions

Revision ID: 396713768fb2
Revises: 65ca290b6e4d
Create Date: 2026-03-31 21:14:12.497239

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '396713768fb2'
down_revision = '65ca290b6e4d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('workout_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_exercise_id', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('workout_sessions', schema=None) as batch_op:
        batch_op.drop_column('last_exercise_id')
