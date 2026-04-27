"""add mini-sessions kind and stats fields

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Branch Labels: None
Depends On: None
"""
from alembic import op
import sqlalchemy as sa

revision = 'j0k1l2m3n4o5'
down_revision = 'i9j0k1l2m3n4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('workouts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mini_kind', sa.String(20), nullable=True))
        batch_op.alter_column('program_week_id', existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table('workout_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('kind', sa.String(20), nullable=False, server_default='main'))

    with op.batch_alter_table('calisthenics_profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('optional_target_per_week', sa.Integer, nullable=False, server_default='0'))


def downgrade():
    with op.batch_alter_table('calisthenics_profiles', schema=None) as batch_op:
        batch_op.drop_column('optional_target_per_week')

    with op.batch_alter_table('workout_sessions', schema=None) as batch_op:
        batch_op.drop_column('kind')

    with op.batch_alter_table('workouts', schema=None) as batch_op:
        batch_op.alter_column('program_week_id', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column('mini_kind')
