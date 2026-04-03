# tests/training/test_progress.py
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.core.models import User
from app.modules.training.models import (
    Exercise, ExerciseRecommendation, LoggedExercise, LoggedSet,
    WorkoutExercise, WorkoutSession, PlannedSet, Workout,
    Mesocycle, ProgramWeek,
)


def _make_user(db):
    u = User(
        telegram_id=80001, name='ProgressTest', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
        level='intermediate', training_days_per_week=3, session_duration_min=60,
        equipment=['full_gym'], onboarding_completed_at=datetime.utcnow(),
    )
    db.session.add(u)
    db.session.commit()
    return u


def _make_exercise(db, name='Bench Press', muscle_group='Chest'):
    ex = Exercise(name=name, muscle_group=muscle_group)
    db.session.add(ex)
    db.session.commit()
    return ex


def _make_session(db, user_id, status='completed', days_ago=0):
    s = WorkoutSession(
        user_id=user_id,
        date=date.today() - timedelta(days=days_ago),
        status=status,
    )
    db.session.add(s)
    db.session.commit()
    return s


def _log_sets(db, session, exercise, sets):
    """sets = list of (reps, weight, rpe)"""
    le = LoggedExercise(session_id=session.id, exercise_id=exercise.id, order_index=0)
    db.session.add(le)
    db.session.flush()
    for i, (reps, weight, rpe) in enumerate(sets, start=1):
        db.session.add(LoggedSet(
            logged_exercise_id=le.id, set_number=i,
            actual_reps=reps, actual_weight_kg=weight, actual_rpe=rpe,
        ))
    db.session.commit()
    return le


def _make_workout_with_planned(db, user_id, exercise, target_reps='8-10', target_weight=60.0):
    """Create a Workout + WorkoutExercise + PlannedSet and attach to session-less workout."""
    from app.modules.training.models import Program
    prog = Program(
        user_id=user_id, name='Test', periodization_type='linear',
        total_weeks=4, status='active',
    )
    db.session.add(prog)
    db.session.flush()
    mc = Mesocycle(program_id=prog.id, name='MC', order_index=0, weeks_count=4)
    db.session.add(mc)
    db.session.flush()
    pw = ProgramWeek(mesocycle_id=mc.id, week_number=1)
    db.session.add(pw)
    db.session.flush()
    w = Workout(program_week_id=pw.id, day_of_week=0, name='Test Workout', order_index=0)
    db.session.add(w)
    db.session.flush()
    we = WorkoutExercise(workout_id=w.id, exercise_id=exercise.id, order_index=0)
    db.session.add(we)
    db.session.flush()
    ps = PlannedSet(
        workout_exercise_id=we.id, set_number=1,
        target_reps=target_reps, target_weight_kg=target_weight, target_rpe=8.0,
    )
    db.session.add(ps)
    db.session.commit()
    return w


def test_increase_weight_at_max_reps_low_rpe(app, db):
    """avg_reps >= target_max AND avg_rpe <= 8 → increase_weight."""
    user = _make_user(db)
    ex = _make_exercise(db, 'Bench Press')
    w = _make_workout_with_planned(db, user.id, ex, target_reps='8-10', target_weight=60.0)
    session = _make_session(db, user.id, status='in_progress')
    session.workout_id = w.id
    db.session.commit()
    # Log 3 sets: all at 10 reps (target_max), RPE 7
    _log_sets(db, session, ex, [(10, 60.0, 7), (10, 60.0, 7), (10, 60.0, 7)])
    session.status = 'completed'
    db.session.commit()

    from app.modules.training.progress import analyze_session_and_recommend
    recs = analyze_session_and_recommend(session.id, user.id)

    assert len(recs) == 1
    assert recs[0].recommendation_type == 'increase_weight'
    assert recs[0].recommended_weight_kg == 62.5  # +2.5kg upper body


def test_increase_reps_in_range_moderate_rpe(app, db):
    """avg_reps in [target_min, target_max) AND avg_rpe <= 8 → increase_reps."""
    user = _make_user(db)
    ex = _make_exercise(db, 'Bench Press 2')
    w = _make_workout_with_planned(db, user.id, ex, target_reps='8-10', target_weight=60.0)
    session = _make_session(db, user.id, status='in_progress')
    session.workout_id = w.id
    db.session.commit()
    # 9 reps (in range but not at max), RPE 7
    _log_sets(db, session, ex, [(9, 60.0, 7), (9, 60.0, 7)])
    session.status = 'completed'
    db.session.commit()

    from app.modules.training.progress import analyze_session_and_recommend
    recs = analyze_session_and_recommend(session.id, user.id)

    assert len(recs) == 1
    assert recs[0].recommendation_type == 'increase_reps'
    assert recs[0].recommended_reps_max == 11  # target_max + 1


def test_maintain_high_rpe_below_target(app, db):
    """avg_rpe >= 9, reps below target → maintain."""
    user = _make_user(db)
    ex = _make_exercise(db, 'Squat High RPE')
    w = _make_workout_with_planned(db, user.id, ex, target_reps='5-6', target_weight=100.0)
    session = _make_session(db, user.id, status='in_progress')
    session.workout_id = w.id
    db.session.commit()
    # Only 4 reps (below min=5), RPE 9.5
    _log_sets(db, session, ex, [(4, 100.0, 9.5), (4, 100.0, 9.5)])
    session.status = 'completed'
    db.session.commit()

    from app.modules.training.progress import analyze_session_and_recommend
    recs = analyze_session_and_recommend(session.id, user.id)

    assert len(recs) == 1
    assert recs[0].recommendation_type == 'maintain'


def test_deload_recommendations_when_deload_needed(app, db):
    """When deload is needed, all recs get type='deload' with weight at 60%."""
    user = _make_user(db)
    ex = _make_exercise(db, 'Deadlift Deload')
    session = _make_session(db, user.id, status='in_progress')
    _log_sets(db, session, ex, [(5, 100.0, 8)])
    session.status = 'completed'
    db.session.commit()

    from app.modules.training.progress import analyze_session_and_recommend
    with patch('app.modules.training.progress.check_deload_needed', return_value=True):
        recs = analyze_session_and_recommend(session.id, user.id)

    assert len(recs) == 1
    assert recs[0].recommendation_type == 'deload'
    assert recs[0].recommended_weight_kg == pytest.approx(60.0)  # 100 * 0.6


def test_no_deload_if_already_deloaded_this_week(app, db):
    """If a 'deload' rec was created in the last 7 days, don't deload again."""
    user = _make_user(db)
    ex = _make_exercise(db, 'Deadlift No Deload')
    # Create a recent deload rec
    recent_deload = ExerciseRecommendation(
        user_id=user.id, exercise_id=ex.id,
        recommendation_type='deload',
        recommended_weight_kg=60.0, recommended_reps_min=5, recommended_reps_max=5,
        reason_text='Deload week',
    )
    db.session.add(recent_deload)
    session = _make_session(db, user.id, status='in_progress')
    _log_sets(db, session, ex, [(5, 100.0, 8)])
    session.status = 'completed'
    db.session.commit()

    from app.modules.training.progress import analyze_session_and_recommend
    with patch('app.modules.training.progress.check_deload_needed', return_value=True):
        recs = analyze_session_and_recommend(session.id, user.id)

    # Should NOT be 'deload' since we just did one
    assert all(r.recommendation_type != 'deload' for r in recs)


def test_decrease_high_rpe_with_pain(app, db):
    """avg_rpe >= 9 + pain journal entry today → decrease weight by 10%."""
    from app.core.models import PainJournal
    user = _make_user(db)
    ex = _make_exercise(db, 'Bench Press Pain')
    w = _make_workout_with_planned(db, user.id, ex, target_reps='5-6', target_weight=100.0)
    session = _make_session(db, user.id, status='in_progress')
    session.workout_id = w.id
    db.session.commit()
    # RPE 9.5 + pain today
    _log_sets(db, session, ex, [(5, 100.0, 9.5), (5, 100.0, 9.5)])
    db.session.add(PainJournal(
        user_id=user.id, date=date.today(),
        body_part='shoulder', pain_type='soreness', intensity=4,
    ))
    session.status = 'completed'
    db.session.commit()

    from app.modules.training.progress import analyze_session_and_recommend
    recs = analyze_session_and_recommend(session.id, user.id)

    assert len(recs) == 1
    assert recs[0].recommendation_type == 'decrease'
    assert recs[0].recommended_weight_kg == 90.0  # 100 * 0.9, rounded to 2.5


def test_stagnation_after_3_identical_sessions(app, db):
    """Same weight + same total reps for 3 consecutive sessions → stagnation."""
    user = _make_user(db)
    ex = _make_exercise(db, 'Stagnation Bench')
    # 2 previous completed sessions with identical sets
    for i in range(1, 3):
        prev = _make_session(db, user.id, status='completed', days_ago=i * 7)
        _log_sets(db, prev, ex, [(8, 80.0, 7), (8, 80.0, 7), (8, 80.0, 7)])
    # Current session: same weight, same reps
    session = _make_session(db, user.id, status='in_progress')
    _log_sets(db, session, ex, [(8, 80.0, 7), (8, 80.0, 7), (8, 80.0, 7)])
    session.status = 'completed'
    db.session.commit()

    from app.modules.training.progress import analyze_session_and_recommend
    recs = analyze_session_and_recommend(session.id, user.id)

    assert len(recs) == 1
    assert recs[0].recommendation_type == 'stagnation'


def test_ai_strategy_change_after_3_stagnations(app, db, mock_anthropic):
    """After 3+ prior stagnation recs for same exercise, type becomes 'change_strategy'."""
    user = _make_user(db)
    ex = _make_exercise(db, 'Stagnation Exercise')

    # Create 3 prior stagnation recs for this exercise
    for _ in range(3):
        db.session.add(ExerciseRecommendation(
            user_id=user.id, exercise_id=ex.id,
            recommendation_type='stagnation',
            recommended_weight_kg=80.0, recommended_reps_min=8, recommended_reps_max=10,
            reason_text='stagnating',
        ))
    db.session.commit()

    # Mock AI response
    mock_anthropic.messages.create.return_value = MagicMock(
        content=[MagicMock(text='Спробуй паузний жим: 2 сек пауза внизу, 3 сети по 6.')]
    )

    # Current session: same weight/reps as always → stagnation triggered
    session = _make_session(db, user.id, status='in_progress')
    _log_sets(db, session, ex, [(8, 80.0, 8), (8, 80.0, 8), (8, 80.0, 8)])

    # 2 prev sessions with same weight+reps for stagnation detection
    for i in range(1, 3):
        prev = _make_session(db, user.id, status='completed', days_ago=i * 7)
        _log_sets(db, prev, ex, [(8, 80.0, 8), (8, 80.0, 8), (8, 80.0, 8)])

    session.status = 'completed'
    db.session.commit()

    from app.modules.training.progress import analyze_session_and_recommend
    with patch('app.modules.training.progress.check_deload_needed', return_value=False):
        recs = analyze_session_and_recommend(session.id, user.id)

    strat_recs = [r for r in recs if r.exercise_id == ex.id]
    assert len(strat_recs) == 1
    assert strat_recs[0].recommendation_type == 'change_strategy'
    assert 'паузний' in strat_recs[0].reason_text


def test_no_ai_call_for_first_stagnation(app, db, mock_anthropic):
    """First stagnation (< 3 prior recs) → type='stagnation', no AI call."""
    user = _make_user(db)
    ex = _make_exercise(db, 'First Stagnation')

    session = _make_session(db, user.id, status='in_progress')
    _log_sets(db, session, ex, [(8, 80.0, 8), (8, 80.0, 8), (8, 80.0, 8)])
    for i in range(1, 3):
        prev = _make_session(db, user.id, status='completed', days_ago=i * 7)
        _log_sets(db, prev, ex, [(8, 80.0, 8), (8, 80.0, 8), (8, 80.0, 8)])
    session.status = 'completed'
    db.session.commit()

    from app.modules.training.progress import analyze_session_and_recommend
    with patch('app.modules.training.progress.check_deload_needed', return_value=False):
        recs = analyze_session_and_recommend(session.id, user.id)

    stag_recs = [r for r in recs if r.exercise_id == ex.id]
    assert stag_recs[0].recommendation_type == 'stagnation'
    mock_anthropic.messages.create.assert_not_called()
