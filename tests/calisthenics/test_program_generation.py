from datetime import datetime
import pytest
from app.core.models import User
from app.modules.calisthenics.models import CalisthenicsProfile, CalisthenicsAssessment
from app.modules.training.models import Program, Workout, Exercise, WorkoutExercise, PlannedSet


def _make_user_with_profile(db, telegram_id=80001):
    u = User(
        telegram_id=telegram_id, name='CaliGen', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
        level='beginner', training_days_per_week=3, session_duration_min=45,
        equipment=['floor', 'bands'], onboarding_completed_at=datetime.utcnow(),
        active_module='calisthenics',
    )
    db.session.add(u)
    db.session.commit()
    p = CalisthenicsProfile(
        user_id=u.id, goals=['muscle'], equipment=['floor', 'bands'],
        days_per_week=3, session_duration_min=45, injuries=[], motivation='look',
    )
    a = CalisthenicsAssessment(
        user_id=u.id, pullups=None, australian_pullups=8, pushups=12,
        pike_pushups=8, squats=20, superman_hold=20, plank=30, hollow_body=15, lunges=12,
    )
    db.session.add_all([p, a])
    db.session.commit()
    return u, p, a


SAMPLE_PROGRAM_DICT = {
    "name": "Calisthenics Foundations",
    "periodization_type": "hypertrophy",
    "total_weeks": 4,
    "mesocycles": [{
        "name": "Block 1",
        "order_index": 0,
        "weeks_count": 1,
        "weeks": [{
            "week_number": 1,
            "notes": None,
            "workouts": [{
                "day_of_week": 0,
                "name": "Push A",
                "order_index": 0,
                "target_muscle_groups": "Chest, Triceps",
                "estimated_duration_min": 35,
                "warmup_notes": "5 min joint mobility",
                "exercises": [{
                    "exercise_name": "full pushup",
                    "order_index": 0,
                    "tempo": "3-1-2-0",
                    "is_mandatory": True,
                    "coaching_notes": "Slow eccentric",
                    "sets": [
                        {"set_number": 1, "target_reps": "8-12", "target_seconds": None,
                         "target_rpe": 7.0, "rest_seconds": 90, "is_amrap": False},
                        {"set_number": 2, "target_reps": "8-12", "target_seconds": None,
                         "target_rpe": 8.0, "rest_seconds": 90, "is_amrap": False},
                        {"set_number": 3, "target_reps": "8-12", "target_seconds": None,
                         "target_rpe": 9.0, "rest_seconds": 90, "is_amrap": True},
                    ],
                }],
            }],
        }],
    }],
}


def test_save_resolves_seeded_exercises(app, db):
    from app.modules.calisthenics.coach import save_calisthenics_program_from_dict
    user, _, _ = _make_user_with_profile(db, telegram_id=80001)
    program = save_calisthenics_program_from_dict(user.id, SAMPLE_PROGRAM_DICT)
    assert program.module == 'calisthenics'
    assert program.status == 'active'
    workout = program.mesocycles[0].weeks[0].workouts[0]
    we = workout.workout_exercises[0]
    ex = db.session.get(Exercise, we.exercise_id)
    assert ex.module == 'calisthenics'
    assert ex.name == 'full pushup'
    assert ex.progression_chain == 'push'
    sets = PlannedSet.query.filter_by(workout_exercise_id=we.id).order_by(PlannedSet.set_number).all()
    assert len(sets) == 3
    assert sets[2].is_amrap is True
    assert sets[0].is_amrap is False


def test_save_archives_previous_active_program(app, db):
    from app.modules.calisthenics.coach import save_calisthenics_program_from_dict
    user, _, _ = _make_user_with_profile(db, telegram_id=80002)
    p1 = save_calisthenics_program_from_dict(user.id, SAMPLE_PROGRAM_DICT)
    assert p1.status == 'active'
    p2 = save_calisthenics_program_from_dict(user.id, SAMPLE_PROGRAM_DICT)
    db.session.refresh(p1)
    assert p1.status == 'completed'
    assert p2.status == 'active'


def test_save_unknown_exercise_raises(app, db):
    from app.modules.calisthenics.coach import save_calisthenics_program_from_dict
    user, _, _ = _make_user_with_profile(db, telegram_id=80003)
    import copy
    bad = copy.deepcopy(SAMPLE_PROGRAM_DICT)
    bad['mesocycles'][0]['weeks'][0]['workouts'][0]['exercises'][0]['exercise_name'] = 'invented galaxy lift'
    with pytest.raises(ValueError, match='invented galaxy lift'):
        save_calisthenics_program_from_dict(user.id, bad)


def test_save_does_not_touch_gym_programs(app, db):
    from app.modules.calisthenics.coach import save_calisthenics_program_from_dict
    user, _, _ = _make_user_with_profile(db, telegram_id=80004)
    gym = Program(user_id=user.id, name='Gym Block', periodization_type='hypertrophy',
                  total_weeks=4, status='active', module='gym')
    db.session.add(gym)
    db.session.commit()
    save_calisthenics_program_from_dict(user.id, SAMPLE_PROGRAM_DICT)
    db.session.refresh(gym)
    assert gym.status == 'active'  # unchanged
