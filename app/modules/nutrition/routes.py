from datetime import date, timedelta
from flask import g, jsonify, request, Response, stream_with_context
from app.core.auth import require_auth
from app.core.models import User, AIConversation
from app.core.ai import stream_chat
from app.extensions import db
from . import bp
from .models import NutritionProfile, MealLog
from .calculator import calc_bmr, calc_tdee, calc_calorie_target, calc_macros, calc_water_ml
from .context import build_nutrition_context


def _compute_and_save(profile: NutritionProfile, user: User) -> None:
    """Recalculate BMR/TDEE/macros and persist to profile."""
    bmr = calc_bmr(user.weight_kg, user.height_cm, user.age, user.gender)
    tdee = calc_tdee(bmr, profile.activity_outside, user.training_days_per_week or 0)
    calorie_target = calc_calorie_target(tdee, user.goal_primary)
    macros = calc_macros(user.weight_kg, calorie_target)
    profile.bmr = round(bmr, 1)
    profile.tdee = round(tdee, 1)
    profile.calorie_target = round(calorie_target, 1)
    profile.protein_g = macros['protein_g']
    profile.fat_g = macros['fat_g']
    profile.carbs_g = macros['carbs_g']


def _profile_to_dict(profile: NutritionProfile, user: User) -> dict:
    return {
        'diet_type':        profile.diet_type,
        'allergies':        profile.allergies or [],
        'cooking_skill':    profile.cooking_skill,
        'budget':           profile.budget,
        'activity_outside': profile.activity_outside,
        'calorie_target':   profile.calorie_target,
        'protein_g':        profile.protein_g,
        'fat_g':            profile.fat_g,
        'carbs_g':          profile.carbs_g,
        'water_ml':         calc_water_ml(user.weight_kg),
    }


@bp.route('/nutrition/profile', methods=['GET'])
@require_auth
def get_nutrition_profile():
    user = db.session.get(User, g.user_id)
    if not user.weight_kg or not user.height_cm:
        return jsonify({'success': False, 'error': {
            'code': 'INCOMPLETE_ONBOARDING',
            'message': 'Complete onboarding first (weight and height required)',
        }}), 400
    profile = NutritionProfile.query.filter_by(user_id=g.user_id).first()
    if not profile:
        return jsonify({'success': True, 'data': None})
    return jsonify({'success': True, 'data': _profile_to_dict(profile, user)})


@bp.route('/nutrition/profile', methods=['POST'])
@require_auth
def set_nutrition_profile():
    user = db.session.get(User, g.user_id)
    if not user.weight_kg or not user.height_cm:
        return jsonify({'success': False, 'error': {
            'code': 'INCOMPLETE_ONBOARDING',
            'message': 'Complete onboarding first (weight and height required)',
        }}), 400
    data = request.json or {}
    profile = NutritionProfile.query.filter_by(user_id=g.user_id).first()
    if not profile:
        profile = NutritionProfile(user_id=g.user_id)
        db.session.add(profile)
    profile.diet_type        = data.get('diet_type', profile.diet_type)
    profile.allergies        = data.get('allergies', profile.allergies)
    profile.cooking_skill    = data.get('cooking_skill', profile.cooking_skill)
    profile.budget           = data.get('budget', profile.budget)
    profile.activity_outside = data.get('activity_outside', profile.activity_outside)
    if not profile.activity_outside:
        return jsonify({'success': False, 'error': {
            'code': 'MISSING_FIELD',
            'message': 'activity_outside is required',
        }}), 400
    _compute_and_save(profile, user)
    db.session.commit()
    return jsonify({'success': True, 'data': _profile_to_dict(profile, user)})


@bp.route('/nutrition/meals/log', methods=['POST'])
@require_auth
def log_meal():
    data = request.json or {}
    description = (data.get('description') or '').strip()
    if not description:
        return jsonify({'success': False, 'error': {
            'code': 'EMPTY', 'message': 'description required',
        }}), 400
    entry = MealLog(user_id=g.user_id, date=date.today(), description=description)
    db.session.add(entry)
    db.session.commit()
    return jsonify({'success': True, 'data': {
        'id': entry.id,
        'date': entry.date.isoformat(),
        'description': entry.description,
    }})


@bp.route('/nutrition/meals/log', methods=['GET'])
@require_auth
def get_meal_log():
    since = date.today() - timedelta(days=14)
    entries = (MealLog.query
               .filter(MealLog.user_id == g.user_id, MealLog.date >= since)
               .order_by(MealLog.date.desc(), MealLog.logged_at.desc())
               .all())
    return jsonify({'success': True, 'data': [
        {
            'id': e.id,
            'date': e.date.isoformat(),
            'description': e.description,
            'logged_at': e.logged_at.isoformat() if e.logged_at else None,
        }
        for e in entries
    ]})


@bp.route('/nutrition/chat/thread', methods=['GET'])
@require_auth
def get_nutrition_thread():
    messages = (AIConversation.query
                .filter_by(user_id=g.user_id, module='nutrition')
                .order_by(AIConversation.created_at.desc())
                .limit(20)
                .all())
    return jsonify({'success': True, 'data': {
        'messages': [
            {'role': m.role, 'content': m.content, 'created_at': m.created_at.isoformat()}
            for m in reversed(messages)
        ],
    }})


@bp.route('/nutrition/chat/message', methods=['POST'])
@require_auth
def nutrition_chat_message():
    data = request.json or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'success': False, 'error': {
            'code': 'EMPTY', 'message': 'content required',
        }}), 400

    nutrition_context = build_nutrition_context(g.user_id)

    def generate():
        for chunk in stream_chat(g.user_id, 'nutrition', content,
                                  extra_context=nutrition_context):
            yield f"data: {chunk.replace(chr(10), ' ')}\n\n"
        yield 'data: [DONE]\n\n'

    return Response(stream_with_context(generate()), mimetype='text/event-stream')
