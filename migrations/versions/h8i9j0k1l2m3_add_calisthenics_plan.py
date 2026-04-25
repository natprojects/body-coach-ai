"""add calisthenics plan columns and seed exercises

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Branch Labels: None
Depends On: None
"""
from alembic import op
import sqlalchemy as sa

revision = 'h8i9j0k1l2m3'
down_revision = 'g7h8i9j0k1l2'
branch_labels = None
depends_on = None


CALI_SEEDS = [
    ('push', 0, 'wall pushup', 'reps'),
    ('push', 1, 'incline pushup', 'reps'),
    ('push', 2, 'knee pushup', 'reps'),
    ('push', 3, 'full pushup', 'reps'),
    ('push', 4, 'diamond pushup', 'reps'),
    ('push', 5, 'decline pushup', 'reps'),
    ('push', 6, 'archer pushup', 'reps'),
    ('push', 7, 'pseudo planche pushup', 'reps'),
    ('push', 8, 'one-arm pushup negative', 'reps'),
    ('push', 9, 'one-arm pushup', 'reps'),

    ('pull', 0, 'dead hang', 'seconds'),
    ('pull', 1, 'scapular pull', 'reps'),
    ('pull', 2, 'australian pullup', 'reps'),
    ('pull', 3, 'negative pullup', 'reps'),
    ('pull', 4, 'band-assisted pullup', 'reps'),
    ('pull', 5, 'full pullup', 'reps'),
    ('pull', 6, 'archer pullup', 'reps'),
    ('pull', 7, 'one-arm pullup negative', 'reps'),

    ('squat', 0, 'assisted squat', 'reps'),
    ('squat', 1, 'full bodyweight squat', 'reps'),
    ('squat', 2, 'bulgarian split squat', 'reps'),
    ('squat', 3, 'pistol squat negative', 'reps'),
    ('squat', 4, 'pistol squat', 'reps'),

    ('core_dynamic', 0, 'dead bug', 'reps'),
    ('core_dynamic', 1, 'hanging knee raise', 'reps'),
    ('core_dynamic', 2, 'hanging leg raise', 'reps'),
    ('core_dynamic', 3, 'toes-to-bar', 'reps'),
    ('core_dynamic', 4, 'dragon flag negative', 'reps'),

    ('core_static', 0, 'forearm plank', 'seconds'),
    ('core_static', 1, 'hollow body hold', 'seconds'),
    ('core_static', 2, 'l-sit tuck', 'seconds'),
    ('core_static', 3, 'l-sit', 'seconds'),
    ('core_static', 4, 'v-sit progression', 'seconds'),

    ('lunge', 0, 'reverse lunge', 'reps'),
    ('lunge', 1, 'walking lunge', 'reps'),
    ('lunge', 2, 'jumping lunge', 'reps'),
    ('lunge', 3, 'shrimp squat regression', 'reps'),
]


def upgrade():
    with op.batch_alter_table('programs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('module', sa.String(20), nullable=False, server_default='gym'))

    with op.batch_alter_table('workout_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('module', sa.String(20), nullable=False, server_default='gym'))

    with op.batch_alter_table('exercises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('module', sa.String(20), nullable=False, server_default='gym'))
        batch_op.add_column(sa.Column('progression_chain', sa.String(30), nullable=True))
        batch_op.add_column(sa.Column('progression_level', sa.Integer, nullable=True))
        batch_op.add_column(sa.Column('unit', sa.String(10), nullable=True))

    with op.batch_alter_table('planned_sets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_amrap', sa.Boolean, nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('target_seconds', sa.Integer, nullable=True))

    with op.batch_alter_table('logged_sets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('actual_seconds', sa.Integer, nullable=True))

    bind = op.get_bind()
    for chain, level, name, unit in CALI_SEEDS:
        bind.execute(sa.text("""
            INSERT OR IGNORE INTO exercises (name, module, progression_chain, progression_level, unit)
            VALUES (:name, 'calisthenics', :chain, :level, :unit)
        """), {'name': name, 'chain': chain, 'level': level, 'unit': unit})


def downgrade():
    bind = op.get_bind()
    seed_names = tuple(row[2] for row in CALI_SEEDS)
    # Delete only the rows we seeded (by name), so any user-added calisthenics exercises survive
    bind.execute(
        sa.text("DELETE FROM exercises WHERE module = 'calisthenics' AND name IN :names")
        .bindparams(sa.bindparam('names', expanding=True)),
        {'names': list(seed_names)},
    )

    with op.batch_alter_table('logged_sets', schema=None) as batch_op:
        batch_op.drop_column('actual_seconds')

    with op.batch_alter_table('planned_sets', schema=None) as batch_op:
        batch_op.drop_column('target_seconds')
        batch_op.drop_column('is_amrap')

    with op.batch_alter_table('exercises', schema=None) as batch_op:
        batch_op.drop_column('unit')
        batch_op.drop_column('progression_level')
        batch_op.drop_column('progression_chain')
        batch_op.drop_column('module')

    with op.batch_alter_table('workout_sessions', schema=None) as batch_op:
        batch_op.drop_column('module')

    with op.batch_alter_table('programs', schema=None) as batch_op:
        batch_op.drop_column('module')
