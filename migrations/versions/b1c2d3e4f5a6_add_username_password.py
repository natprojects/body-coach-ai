"""add username and password_hash to users

Revision ID: b1c2d3e4f5a6
Revises: 92312803e936
Create Date: 2026-03-30

"""
from alembic import op
import sqlalchemy as sa

revision = 'b1c2d3e4f5a6'
down_revision = '92312803e936'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('username', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('password_hash', sa.String(256), nullable=True))
    with op.batch_alter_table('users') as batch_op:
        batch_op.create_unique_constraint('uq_users_username', ['username'])


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_constraint('uq_users_username', type_='unique')
    op.drop_column('users', 'password_hash')
    op.drop_column('users', 'username')
