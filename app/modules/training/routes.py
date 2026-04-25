from datetime import datetime, date, timedelta
from flask import g, jsonify, request, Response, stream_with_context
from app.core.auth import require_auth
from app.core.ai import stream_chat
from app.core.models import User
from app.extensions import db
from . import bp
from .onboarding import ONBOARDING_STEPS, apply_step, get_first_step, get_next_step
from .coach import build_training_context, generate_program, save_program_from_dict
from .models import Program, Mesocycle, LoggedExercise, LoggedSet, Workout, WorkoutSession, ProgramWeek
from .progress import generate_post_workout_feedback, generate_weekly_report


# ── Onboarding ────────────────────────────────────────────────────────────────

@bp.route('/onboarding/status', methods=['GET'])
@require_auth
def onboarding_status():
    user = User.query.get(g.user_id)
    completed = user.onboarding_completed_at is not None
    return jsonify({'success': True, 'data': {
        'completed': completed,
        'next_step': None if completed else get_first_step(user),
        'steps': ONBOARDING_STEPS,
    }})


@bp.route('/onboarding/step', methods=['POST'])
@require_auth
def onboarding_step():
    user = User.query.get(g.user_id)
    data = request.json or {}
    step = data.get('step')
    step_data = data.get('data', {})
    try:
        apply_step(user, step, step_data)
    except ValueError as e:
        return jsonify({'success': False, 'error': {'code': 'BAD_REQUEST', 'message': str(e)}}), 400
    next_step = get_next_step(user, step)
    return jsonify({'success': True, 'data': {'next_step': next_step}})


@bp.route('/onboarding/complete', methods=['POST'])
@require_auth
def onboarding_complete():
    user = User.query.get(g.user_id)
    user.onboarding_completed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'data': {'completed': True}})


# ── Ping (keep for health check) ───────────────────────────────────────────────

@bp.route('/training/ping', methods=['GET'])
def ping():
    return jsonify({'success': True, 'data': 'training module online'})


# ── Program ───────────────────────────────────────────────────────────────────

@bp.route('/training/program/generate', methods=['POST'])
@require_auth
def program_generate():
    user = db.session.get(User, g.user_id)
    if not user.onboarding_completed_at:
        return jsonify({'success': False, 'error': {
            'code': 'BAD_REQUEST', 'message': 'Complete onboarding first'
        }}), 400
    try:
        program_dict = generate_program(user)
    except ValueError as e:
        return jsonify({'success': False, 'error': {
            'code': 'AI_ERROR', 'message': 'Failed to generate program. Please try again.'
        }}), 500
    program = save_program_from_dict(user.id, program_dict)
    return jsonify({'success': True, 'data': {
        'program_id': program.id,
        'name': program.name,
        'total_weeks': program.total_weeks,
        'periodization_type': program.periodization_type,
    }})


@bp.route('/training/program/current', methods=['GET'])
@require_auth
def program_current():
    user = db.session.get(User, g.user_id)
    program = Program.query.filter_by(user_id=g.user_id, status='active', module=user.active_module).first()
    if not program:
        return jsonify({'success': True, 'data': None})
    return jsonify({'success': True, 'data': _serialize_program(program)})


@bp.route('/training/program/week/<int:week_num>', methods=['GET'])
@require_auth
def program_week(week_num):
    user = db.session.get(User, g.user_id)
    program = Program.query.filter_by(user_id=g.user_id, status='active', module=user.active_module).first()
    if not program:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'No active program'}}), 404
    from .models import ProgramWeek
    week = (ProgramWeek.query
            .join(Mesocycle)
            .filter(Mesocycle.program_id == program.id, ProgramWeek.week_number == week_num)
            .first())
    if not week:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': f'Week {week_num} not found'}}), 404
    return jsonify({'success': True, 'data': _serialize_week(week)})


def _serialize_program(program):
    return {
        'id': program.id,
        'name': program.name,
        'periodization_type': program.periodization_type,
        'total_weeks': program.total_weeks,
        'status': program.status,
        'mesocycles': [{
            'id': m.id, 'name': m.name, 'order_index': m.order_index, 'weeks_count': m.weeks_count
        } for m in program.mesocycles],
    }


def _serialize_week(week):
    return {
        'week_number': week.week_number,
        'notes': week.notes,
        'workouts': [{
            'id': w.id, 'day_of_week': w.day_of_week, 'name': w.name,
            'exercises': [{
                'exercise_name': we.exercise.name,
                'notes': we.notes,
                'sets': [{
                    'set_number': ps.set_number,
                    'target_reps': ps.target_reps,
                    'target_weight_kg': ps.target_weight_kg,
                    'target_rpe': ps.target_rpe,
                    'rest_seconds': ps.rest_seconds,
                } for ps in we.planned_sets]
            } for we in w.workout_exercises]
        } for w in week.workouts]
    }


def _get_active_workout(week, user_id, today, active_module):
    """Return (workout, is_ad_hoc). is_ad_hoc=True when training on unscheduled day."""
    today_dow = today.weekday()

    # 1. Scheduled workout today
    scheduled = Workout.query.filter_by(
        program_week_id=week.id, day_of_week=today_dow
    ).first()
    if scheduled:
        return scheduled, False

    # 2. Next incomplete workout this week
    week_workouts = (Workout.query
                     .filter_by(program_week_id=week.id)
                     .order_by(Workout.order_index)
                     .all())
    if not week_workouts:
        return None, False

    completed_ids = {
        s.workout_id for s in
        WorkoutSession.query.filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.module == active_module,
            WorkoutSession.workout_id.in_([w.id for w in week_workouts]),
            WorkoutSession.status == 'completed',
        ).all()
    }
    for w in week_workouts:
        if w.id not in completed_ids:
            return w, True

    return None, False


# ── Today's workout ───────────────────────────────────────────────────────────

@bp.route('/training/today', methods=['GET'])
@require_auth
def training_today():
    user = db.session.get(User, g.user_id)
    program = Program.query.filter_by(user_id=g.user_id, status='active', module=user.active_module).first()
    if not program:
        return jsonify({'success': True, 'data': None})

    today = date.today()
    days_elapsed = (today - program.created_at.date()).days
    current_week_num = (days_elapsed // 7) + 1

    week = (ProgramWeek.query
            .join(Mesocycle)
            .filter(Mesocycle.program_id == program.id, ProgramWeek.week_number == current_week_num)
            .first())
    if not week:
        return jsonify({'success': True, 'data': None})

    workout, is_ad_hoc = _get_active_workout(week, g.user_id, today, user.active_module)
    if not workout:
        return jsonify({'success': True, 'data': {'rest_day': True}})

    data = _serialize_workout_with_sets(workout)
    if is_ad_hoc:
        data['ad_hoc'] = True
    return jsonify({'success': True, 'data': data})


def _serialize_workout_with_sets(workout: Workout) -> dict:
    return {
        'id': workout.id,
        'name': workout.name,
        'day_of_week': workout.day_of_week,
        'exercises': [{
            'exercise_id': we.exercise_id,
            'exercise_name': we.exercise.name,
            'order_index': we.order_index,
            'coaching_notes': we.notes,
            'selection_reason': we.selection_reason,
            'tempo': we.tempo,
            'muscle_group': we.exercise.muscle_group,
            'sets': [{
                'set_number': ps.set_number,
                'target_reps': ps.target_reps,
                'target_weight_kg': ps.target_weight_kg,
                'target_rpe': ps.target_rpe,
                'rest_seconds': ps.rest_seconds,
            } for ps in we.planned_sets]
        } for we in workout.workout_exercises]
    }


# ── Session ───────────────────────────────────────────────────────────────────

@bp.route('/training/session/start', methods=['POST'])
@require_auth
def session_start():
    data = request.json or {}
    _phase = data.get('cycle_phase')
    _VALID_PHASES = {'menstrual', 'follicular', 'ovulation', 'luteal'}
    user = db.session.get(User, g.user_id)
    session = WorkoutSession(
        user_id=g.user_id,
        workout_id=data.get('workout_id'),
        module=user.active_module,
        date=date.today(),
        status='in_progress',
        cycle_phase=_phase if _phase in _VALID_PHASES else None,
        cycle_adapted=bool(data.get('cycle_adapted', False)),
    )
    db.session.add(session)
    db.session.commit()
    return jsonify({'success': True, 'data': {'session_id': session.id}})


@bp.route('/training/session/log-set', methods=['POST'])
@require_auth
def session_log_set():
    data = request.json or {}
    session_id = data.get('session_id')
    exercise_id = data.get('exercise_id')

    # Verify session belongs to authenticated user
    _user = db.session.get(User, g.user_id)
    session = WorkoutSession.query.filter_by(id=session_id, user_id=g.user_id, module=_user.active_module).first()
    if not session:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Session not found'}}), 404

    le = LoggedExercise.query.filter_by(session_id=session_id, exercise_id=exercise_id).first()
    if not le:
        existing_count = LoggedExercise.query.filter_by(session_id=session_id).count()
        le = LoggedExercise(session_id=session_id, exercise_id=exercise_id, order_index=existing_count)
        db.session.add(le)
        db.session.flush()

    ls = LoggedSet(
        logged_exercise_id=le.id,
        set_number=data.get('set_number', 1),
        actual_reps=data.get('actual_reps'),
        actual_weight_kg=data.get('actual_weight_kg'),
        actual_rpe=data.get('actual_rpe'),
        notes=data.get('notes'),
    )
    db.session.add(ls)
    session.last_exercise_id = exercise_id
    db.session.commit()
    return jsonify({'success': True, 'data': {'logged_set_id': ls.id}})


@bp.route('/training/session/active', methods=['GET'])
@require_auth
def session_active():
    _user = db.session.get(User, g.user_id)
    session = (WorkoutSession.query
               .filter_by(user_id=g.user_id, status='in_progress', module=_user.active_module)
               .order_by(WorkoutSession.id.desc())
               .first())
    if not session:
        return jsonify({'success': True, 'data': None})

    logged = {}
    for le in session.logged_exercises:
        logged[le.exercise_id] = [{
            'set_number': s.set_number,
            'actual_reps': s.actual_reps,
            'actual_weight_kg': s.actual_weight_kg,
            'actual_rpe': s.actual_rpe,
        } for s in le.logged_sets]

    workout_data = None
    if session.workout_id:
        workout = Workout.query.get(session.workout_id)
        if workout:
            workout_data = _serialize_workout_with_sets(workout)

    return jsonify({'success': True, 'data': {
        'session_id': session.id,
        'workout_id': session.workout_id,
        'date': session.date.isoformat(),
        'last_exercise_id': session.last_exercise_id,
        'logged': logged,
        'workout': workout_data,
    }})


@bp.route('/training/session/complete', methods=['POST'])
@require_auth
def session_complete():
    data = request.json or {}
    _user = db.session.get(User, g.user_id)
    session = WorkoutSession.query.filter_by(id=data.get('session_id'), user_id=g.user_id, module=_user.active_module).first()
    if not session:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Session not found'}}), 404

    session.status = 'completed'
    # Close any other stale in-progress sessions for this user
    WorkoutSession.query.filter(
        WorkoutSession.user_id == g.user_id,
        WorkoutSession.status == 'in_progress',
        WorkoutSession.module == _user.active_module,
        WorkoutSession.id != session.id,
    ).update({'status': 'abandoned'})
    db.session.commit()

    feedback = generate_post_workout_feedback(session, g.user_id)
    session.ai_feedback = feedback
    db.session.commit()

    from .progress import analyze_session_and_recommend
    recs = analyze_session_and_recommend(session.id, g.user_id)
    rec_data = [{
        'exercise_id': r.exercise_id,
        'exercise_name': r.exercise.name,
        'recommended_weight_kg': r.recommended_weight_kg,
        'recommended_reps_min': r.recommended_reps_min,
        'recommended_reps_max': r.recommended_reps_max,
        'recommendation_type': r.recommendation_type,
        'reason_text': r.reason_text,
    } for r in recs]

    return jsonify({'success': True, 'data': {
        'session_id': session.id,
        'feedback': feedback,
        'next_session_plan': rec_data,
    }})


@bp.route('/training/session/<int:session_id>', methods=['GET'])
@require_auth
def session_detail(session_id):
    _user = db.session.get(User, g.user_id)
    session = WorkoutSession.query.filter_by(id=session_id, user_id=g.user_id, module=_user.active_module).first()
    if not session:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Session not found'}}), 404
    return jsonify({'success': True, 'data': {
        'id': session.id,
        'date': session.date.isoformat(),
        'status': session.status,
        'ai_feedback': session.ai_feedback,
        'exercises': [{
            'exercise_name': le.exercise.name,
            'sets': [{
                'set_number': s.set_number,
                'actual_reps': s.actual_reps,
                'actual_weight_kg': s.actual_weight_kg,
                'actual_rpe': s.actual_rpe,
            } for s in le.logged_sets]
        } for le in session.logged_exercises]
    }})


# ── Progress ──────────────────────────────────────────────────────────────────

@bp.route('/training/progress/weekly', methods=['GET'])
@require_auth
def progress_weekly():
    since = date.today() - timedelta(days=7)
    _user = db.session.get(User, g.user_id)
    sessions = (WorkoutSession.query
                .filter(WorkoutSession.user_id == g.user_id,
                        WorkoutSession.date >= since,
                        WorkoutSession.status == 'completed',
                        WorkoutSession.module == _user.active_module)
                .order_by(WorkoutSession.date)
                .all())
    report = generate_weekly_report(g.user_id, sessions)
    return jsonify({'success': True, 'data': {'report': report}})


@bp.route('/training/progress/history', methods=['GET'])
@require_auth
def progress_history():
    _user = db.session.get(User, g.user_id)
    sessions = (WorkoutSession.query
                .filter_by(user_id=g.user_id, module=_user.active_module)
                .order_by(WorkoutSession.date.desc())
                .limit(50)
                .all())
    return jsonify({'success': True, 'data': [{
        'id': s.id, 'date': s.date.isoformat(),
        'status': s.status, 'workout_id': s.workout_id,
    } for s in sessions]})


# ── AI Chat ───────────────────────────────────────────────────────────────────

@bp.route('/training/chat', methods=['POST'])
@require_auth
def training_chat():
    data = request.json or {}
    message = data.get('message', '')
    session_id = data.get('session_id')  # optional

    extra_context = build_training_context(g.user_id, session_id=session_id)

    def generate():
        for chunk in stream_chat(g.user_id, 'training', message, extra_context=extra_context):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


def _serialize_program_full(program):
    from datetime import date
    from .models import WorkoutExercise, Workout, ProgramWeek
    days_elapsed = (date.today() - program.created_at.date()).days
    current_week = min((days_elapsed // 7) + 1, program.total_weeks)

    total_wes = (WorkoutExercise.query
                 .join(Workout).join(ProgramWeek).join(Mesocycle)
                 .filter(Mesocycle.program_id == program.id).count())
    filled_wes = (WorkoutExercise.query
                  .join(Workout).join(ProgramWeek).join(Mesocycle)
                  .filter(Mesocycle.program_id == program.id,
                          WorkoutExercise.selection_reason.isnot(None)).count())
    insights_generated = total_wes > 0 and filled_wes == total_wes

    return {
        'id': program.id,
        'name': program.name,
        'periodization_type': program.periodization_type,
        'total_weeks': program.total_weeks,
        'current_week': current_week,
        'insights_generated': insights_generated,
        'mesocycles': [{
            'id': m.id,
            'name': m.name,
            'order_index': m.order_index,
            'weeks_count': m.weeks_count,
            'weeks': [{
                'week_number': w.week_number,
                'notes': w.notes,
                'workouts': [{
                    'id': wo.id,
                    'name': wo.name,
                    'day_of_week': wo.day_of_week,
                    'order_index': wo.order_index,
                    'target_muscle_groups': wo.target_muscle_groups,
                    'estimated_duration_min': wo.estimated_duration_min,
                    'warmup_notes': wo.warmup_notes,
                    'exercises': [{
                        'workout_exercise_id': we.id,
                        'exercise_name': we.exercise.name,
                        'order_index': we.order_index,
                        'tempo': we.tempo,
                        'is_mandatory': we.is_mandatory,
                        'coaching_notes': we.notes,
                        'selection_reason': we.selection_reason,
                        'expected_outcome': we.expected_outcome,
                        'modifications_applied': we.modifications_applied,
                        'sets': [{
                            'set_number': ps.set_number,
                            'target_reps': ps.target_reps,
                            'target_weight_kg': ps.target_weight_kg,
                            'target_rpe': ps.target_rpe,
                            'rest_seconds': ps.rest_seconds,
                        } for ps in we.planned_sets]
                    } for we in wo.workout_exercises]
                } for wo in w.workouts]
            } for w in m.weeks]
        } for m in program.mesocycles]
    }


@bp.route('/training/program/full', methods=['GET'])
@require_auth
def program_full():
    user = db.session.get(User, g.user_id)
    program = Program.query.filter_by(user_id=g.user_id, status='active', module=user.active_module).first()
    if not program:
        return jsonify({'success': True, 'data': None})
    return jsonify({'success': True, 'data': _serialize_program_full(program)})


@bp.route('/training/program/insights', methods=['POST'])
@require_auth
def program_insights():
    _user_for_insights = db.session.get(User, g.user_id)
    program = Program.query.filter_by(user_id=g.user_id, status='active', module=_user_for_insights.active_module).first()
    if not program:
        return jsonify({'success': False, 'error': {
            'code': 'NOT_FOUND', 'message': 'No active program'
        }}), 404

    from .models import WorkoutExercise, Workout, ProgramWeek
    total = (WorkoutExercise.query
             .join(Workout).join(ProgramWeek).join(Mesocycle)
             .filter(Mesocycle.program_id == program.id).count())
    filled = (WorkoutExercise.query
              .join(Workout).join(ProgramWeek).join(Mesocycle)
              .filter(Mesocycle.program_id == program.id,
                      WorkoutExercise.selection_reason.isnot(None)).count())

    if total > 0 and filled == total:
        return jsonify({'success': True, 'data': {'count': total, 'already_done': True}})

    from .coach import generate_exercise_insights
    try:
        count = generate_exercise_insights(program, _user_for_insights)
    except Exception:
        return jsonify({'success': False, 'error': {
            'code': 'AI_ERROR', 'message': 'Failed to generate insights, please try again.'
        }}), 500

    return jsonify({'success': True, 'data': {'count': count, 'already_done': False}})


@bp.route('/training/session/skip-exercise', methods=['POST'])
@require_auth
def session_skip_exercise():
    data = request.json or {}
    _user = db.session.get(User, g.user_id)
    session = WorkoutSession.query.filter_by(id=data.get('session_id'), user_id=g.user_id, module=_user.active_module).first()
    if not session:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Session not found'}}), 404
    reason = data.get('reason', 'skipped')
    note = f"Skipped {data.get('exercise_name', data.get('exercise_id', ''))}: {reason}"
    session.notes = ((session.notes or '') + '\n' + note).strip()
    db.session.commit()
    return jsonify({'success': True})


@bp.route('/training/exercise/<int:exercise_id>/alternatives', methods=['GET'])
@require_auth
def exercise_alternatives(exercise_id):
    from .models import Exercise
    ex = db.session.get(Exercise, exercise_id)
    if not ex:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Exercise not found'}}), 404
    alts = (Exercise.query
            .filter(Exercise.muscle_group == ex.muscle_group, Exercise.id != exercise_id)
            .limit(4).all())
    if len(alts) >= 2:
        return jsonify({'success': True, 'data': {'alternatives': [
            {'exercise_id': a.id, 'exercise_name': a.name} for a in alts[:3]
        ]}})
    user = db.session.get(User, g.user_id)
    from .coach import suggest_exercise_alternatives
    alts_list = suggest_exercise_alternatives(ex, user)
    return jsonify({'success': True, 'data': {'alternatives': alts_list}})


@bp.route('/training/exercise/<int:exercise_id>/technique', methods=['GET'])
@require_auth
def exercise_technique(exercise_id):
    from .models import Exercise, WorkoutExercise, Workout, ProgramWeek
    ex = db.session.get(Exercise, exercise_id)
    if not ex:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Exercise not found'}}), 404
    user = db.session.get(User, g.user_id)
    program = Program.query.filter_by(user_id=g.user_id, status='active', module=user.active_module).first()
    coaching_notes = None
    if program:
        we = (WorkoutExercise.query
              .join(Workout).join(ProgramWeek).join(Mesocycle)
              .filter(Mesocycle.program_id == program.id, WorkoutExercise.exercise_id == exercise_id)
              .first())
        if we and we.notes:
            coaching_notes = we.notes
    if ex.technique_text:
        return jsonify({'success': True, 'data': {'technique': ex.technique_text}})
    from .coach import get_exercise_technique
    technique = get_exercise_technique(ex, user, coaching_notes)
    ex.technique_text = technique
    db.session.commit()
    return jsonify({'success': True, 'data': {'technique': technique}})


@bp.route('/training/recommendations/today', methods=['GET'])
@require_auth
def recommendations_today():
    from .models import ExerciseRecommendation, LoggedExercise
    from .progress import check_deload_needed

    _user = db.session.get(User, g.user_id)
    program = Program.query.filter_by(user_id=g.user_id, status='active', module=_user.active_module).first()
    if not program:
        return jsonify({'success': True, 'data': {'recommendations': [], 'deload_needed': False}})

    today = date.today()
    days_elapsed = (today - program.created_at.date()).days
    current_week_num = min((days_elapsed // 7) + 1, program.total_weeks)

    week = (ProgramWeek.query
            .join(Mesocycle)
            .filter(Mesocycle.program_id == program.id,
                    ProgramWeek.week_number == current_week_num)
            .first())
    if not week:
        return jsonify({'success': True, 'data': {'recommendations': [], 'deload_needed': False}})

    workout, _ = _get_active_workout(week, g.user_id, today, _user.active_module)
    if not workout:
        return jsonify({'success': True, 'data': {'recommendations': [], 'deload_needed': False}})

    recs = []
    for we in workout.workout_exercises:
        # Latest recommendation for this exercise
        rec = (ExerciseRecommendation.query
               .filter_by(user_id=g.user_id, exercise_id=we.exercise_id)
               .order_by(ExerciseRecommendation.created_at.desc())
               .first())

        # Last logged session for this exercise
        last_le = (LoggedExercise.query
                   .join(WorkoutSession)
                   .filter(
                       LoggedExercise.exercise_id == we.exercise_id,
                       WorkoutSession.user_id == g.user_id,
                       WorkoutSession.status == 'completed',
                   )
                   .order_by(WorkoutSession.date.desc())
                   .first())

        last_data = None
        if last_le and last_le.logged_sets:
            s = last_le.logged_sets[0]
            total_reps = sum(ls.actual_reps or 0 for ls in last_le.logged_sets)
            last_data = {
                'weight_kg': s.actual_weight_kg,
                'reps': total_reps // len(last_le.logged_sets) if last_le.logged_sets else s.actual_reps,
                'rpe': sum(ls.actual_rpe or 0 for ls in last_le.logged_sets) / len(last_le.logged_sets),
            }

        if rec:
            recs.append({
                'exercise_id': we.exercise_id,
                'exercise_name': we.exercise.name,
                'order_index': we.order_index,
                'last': last_data,
                'recommended_weight_kg': rec.recommended_weight_kg,
                'recommended_reps_min': rec.recommended_reps_min,
                'recommended_reps_max': rec.recommended_reps_max,
                'recommendation_type': rec.recommendation_type,
                'reason_text': rec.reason_text,
            })
        else:
            # No history — show planned targets
            ps = we.planned_sets[0] if we.planned_sets else None
            reps_str = ps.target_reps if ps else None
            reps_min = reps_max = None
            if reps_str:
                parts = str(reps_str).split('-')
                try:
                    reps_min = int(parts[0])
                    reps_max = int(parts[-1])
                except (ValueError, IndexError):
                    pass
            recs.append({
                'exercise_id': we.exercise_id,
                'exercise_name': we.exercise.name,
                'order_index': we.order_index,
                'last': None,
                'recommended_weight_kg': ps.target_weight_kg if ps else None,
                'recommended_reps_min': reps_min,
                'recommended_reps_max': reps_max,
                'recommendation_type': 'planned',
                'reason_text': 'First session — use planned targets.',
            })

    deload_needed = check_deload_needed(g.user_id)

    return jsonify({'success': True, 'data': {
        'recommendations': recs,
        'deload_needed': deload_needed,
    }})


@bp.route('/training/cycle/phase', methods=['GET'])
@require_auth
def cycle_phase_check():
    from app.modules.training.cycle import get_cycle_phase, get_cycle_adaptations
    phase_data = get_cycle_phase(g.user_id)
    if not phase_data.get('phase'):
        # tracking disabled or no data
        return jsonify({'success': True, 'data': phase_data})
    adaptations = []
    if phase_data.get('show_card') and phase_data['phase'] in ('ovulation', 'luteal', 'menstrual'):
        adaptations = get_cycle_adaptations(
            g.user_id,
            phase_data['phase'],
            phase_data['modifier'],
        )
    phase_data['adaptations'] = adaptations
    return jsonify({'success': True, 'data': phase_data})
