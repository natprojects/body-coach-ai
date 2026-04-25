"""add calisthenics tables and active_module

Revision ID: g7h8i9j0k1l2
Revises: a1b2c3d4e5f6
Branch Labels: None
Depends On: None
"""
from alembic import op
import sqlalchemy as sa

revision = 'g7h8i9j0k1l2'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Add active_module to users
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('active_module', sa.String(20), nullable=False, server_default='gym')
        )

    # Create calisthenics_profiles
    op.create_table(
        'calisthenics_profiles',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), unique=True, nullable=False),
        sa.Column('goals', sa.JSON, nullable=True),
        sa.Column('equipment', sa.JSON, nullable=True),
        sa.Column('days_per_week', sa.Integer, nullable=True),
        sa.Column('session_duration_min', sa.Integer, nullable=True),
        sa.Column('injuries', sa.JSON, nullable=True),
        sa.Column('motivation', sa.String(50), nullable=True),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
    )

    # Create calisthenics_assessments
    op.create_table(
        'calisthenics_assessments',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('assessed_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('pullups', sa.Integer, nullable=True),
        sa.Column('australian_pullups', sa.Integer, nullable=True),
        sa.Column('pushups', sa.Integer, nullable=True),
        sa.Column('pike_pushups', sa.Integer, nullable=True),
        sa.Column('squats', sa.Integer, nullable=True),
        sa.Column('superman_hold', sa.Integer, nullable=True),
        sa.Column('plank', sa.Integer, nullable=True),
        sa.Column('hollow_body', sa.Integer, nullable=True),
        sa.Column('lunges', sa.Integer, nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
    )


def downgrade():
    op.drop_table('calisthenics_assessments')
    op.drop_table('calisthenics_profiles')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('active_module')
