def test_program_mesocycle_hierarchy(db, app):
    from app.core.models import User
    from app.modules.training.models import (
        Exercise, LoggedExercise, LoggedSet, Mesocycle,
        PlannedSet, Program, ProgramWeek, Workout, WorkoutExercise, WorkoutSession
    )
    from datetime import date

    user = User(telegram_id=40001)
    db.session.add(user)
    db.session.commit()

    program = Program(user_id=user.id, name='4-Week Hypertrophy', periodization_type='block', total_weeks=4)
    db.session.add(program)
    db.session.commit()

    meso = Mesocycle(program_id=program.id, name='Accumulation', order_index=0, weeks_count=3)
    db.session.add(meso)
    db.session.commit()

    week = ProgramWeek(mesocycle_id=meso.id, week_number=1)
    db.session.add(week)
    db.session.commit()

    workout = Workout(program_week_id=week.id, day_of_week=0, name='Upper Body A', order_index=0)
    db.session.add(workout)
    db.session.commit()

    exercise = Exercise(name='Bench Press', muscle_group='chest', equipment_needed='barbell',
                        contraindication_severity='none', is_corrective=False, is_prehab=False)
    db.session.add(exercise)
    db.session.commit()

    we = WorkoutExercise(workout_id=workout.id, exercise_id=exercise.id, order_index=0)
    db.session.add(we)
    db.session.commit()

    ps = PlannedSet(workout_exercise_id=we.id, set_number=1,
                    target_reps='8-10', target_weight_kg=60.0, target_rpe=7.0, rest_seconds=120)
    db.session.add(ps)
    db.session.commit()

    # Verify hierarchy via relationships
    assert len(program.mesocycles) == 1
    assert len(program.mesocycles[0].weeks) == 1
    assert len(program.mesocycles[0].weeks[0].workouts) == 1

    # Session logging
    session = WorkoutSession(user_id=user.id, workout_id=workout.id, date=date.today())
    db.session.add(session)
    db.session.commit()

    le = LoggedExercise(session_id=session.id, exercise_id=exercise.id, order_index=0)
    db.session.add(le)
    db.session.commit()

    ls = LoggedSet(logged_exercise_id=le.id, set_number=1, actual_reps=9, actual_weight_kg=62.5, actual_rpe=7.5)
    db.session.add(ls)
    db.session.commit()

    assert ls.actual_weight_kg == 62.5
    assert session.status == 'in_progress'
