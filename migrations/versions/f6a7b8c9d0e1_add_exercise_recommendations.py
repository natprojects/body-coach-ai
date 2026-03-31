"""add exercise_recommendations table

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'exercise_recommendations',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('exercise_id', sa.Integer, sa.ForeignKey('exercises.id'), nullable=False),
        sa.Column('session_id', sa.Integer, sa.ForeignKey('workout_sessions.id'), nullable=True),
        sa.Column('recommended_weight_kg', sa.Float, nullable=True),
        sa.Column('recommended_reps_min', sa.Integer, nullable=True),
        sa.Column('recommended_reps_max', sa.Integer, nullable=True),
        sa.Column('recommendation_type', sa.String(30), nullable=False),
        sa.Column('reason_text', sa.Text, nullable=True),
        sa.Column('is_applied', sa.Boolean, default=False, server_default='0'),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('exercise_recommendations')
