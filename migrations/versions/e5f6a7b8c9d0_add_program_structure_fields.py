"""add program structure fields

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('workouts') as batch_op:
        batch_op.add_column(sa.Column('target_muscle_groups', sa.String(200), nullable=True))
        batch_op.add_column(sa.Column('estimated_duration_min', sa.Integer, nullable=True))
        batch_op.add_column(sa.Column('warmup_notes', sa.Text, nullable=True))

    with op.batch_alter_table('workout_exercises') as batch_op:
        batch_op.add_column(sa.Column('tempo', sa.String(20), nullable=True))
        batch_op.add_column(sa.Column('is_mandatory', sa.Boolean, nullable=True, server_default='1'))


def downgrade():
    with op.batch_alter_table('workout_exercises') as batch_op:
        batch_op.drop_column('is_mandatory')
        batch_op.drop_column('tempo')

    with op.batch_alter_table('workouts') as batch_op:
        batch_op.drop_column('warmup_notes')
        batch_op.drop_column('estimated_duration_min')
        batch_op.drop_column('target_muscle_groups')
