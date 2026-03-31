"""add insight columns to workout_exercises

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('workout_exercises') as batch_op:
        batch_op.add_column(sa.Column('selection_reason', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('expected_outcome', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('modifications_applied', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('workout_exercises') as batch_op:
        batch_op.drop_column('modifications_applied')
        batch_op.drop_column('expected_outcome')
        batch_op.drop_column('selection_reason')
