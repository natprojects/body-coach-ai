"""add nutrition tables

Revision ID: a1b2c3d4e5f6
Revises: 3ee87c1b43f1
Create Date: 2026-04-05 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '3ee87c1b43f1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'nutrition_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('diet_type', sa.String(20), nullable=True),
        sa.Column('allergies', sa.JSON(), nullable=True),
        sa.Column('cooking_skill', sa.String(20), nullable=True),
        sa.Column('budget', sa.String(20), nullable=True),
        sa.Column('activity_outside', sa.String(20), nullable=True),
        sa.Column('bmr', sa.Float(), nullable=True),
        sa.Column('tdee', sa.Float(), nullable=True),
        sa.Column('calorie_target', sa.Float(), nullable=True),
        sa.Column('protein_g', sa.Float(), nullable=True),
        sa.Column('fat_g', sa.Float(), nullable=True),
        sa.Column('carbs_g', sa.Float(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_table(
        'meal_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('logged_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('meal_logs')
    op.drop_table('nutrition_profiles')
