"""Seed calisthenics exercises for coach tests that need them."""
import pytest
from app.modules.training.models import Exercise
from app.extensions import db as _db

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


@pytest.fixture(autouse=True)
def seed_calisthenics_exercises(app):
    """Insert seeded calisthenics exercises into the test DB for every test in this directory."""
    with app.app_context():
        for chain, level, name, unit in CALI_SEEDS:
            if not Exercise.query.filter_by(module='calisthenics', name=name).first():
                _db.session.add(Exercise(
                    name=name,
                    module='calisthenics',
                    progression_chain=chain,
                    progression_level=level,
                    unit=unit,
                ))
        _db.session.commit()
