from __future__ import annotations

from datetime import datetime
from app.extensions import db
from app.core.models import User

ONBOARDING_STEPS = [
    'basic_data',
    'goals',
    'training_experience',
    'physical_characteristics',
    'menstrual_cycle',
    'training_style',
    'psychology',
    'previous_program',
    'body_measurements',
]


def get_first_step(user: User) -> str:
    return ONBOARDING_STEPS[0]


def get_next_step(user: User, current_step: str) -> str | None:
    steps = ONBOARDING_STEPS.copy()
    if user.gender != 'female':
        steps = [s for s in steps if s != 'menstrual_cycle']
    if current_step not in steps:
        return steps[0]
    idx = steps.index(current_step)
    return steps[idx + 1] if idx + 1 < len(steps) else None


def apply_step(user: User, step: str, data: dict) -> None:
    handlers = {
        'basic_data': _apply_basic_data,
        'goals': _apply_goals,
        'training_experience': _apply_training_experience,
        'physical_characteristics': _apply_physical_characteristics,
        'menstrual_cycle': _apply_menstrual_cycle,
        'training_style': _apply_training_style,
        'psychology': _apply_psychology,
        'previous_program': _apply_previous_program,
        'body_measurements': _apply_body_measurements,
    }
    if step not in handlers:
        raise ValueError(f"Unknown step: {step}")
    handlers[step](user, data)
    db.session.commit()


def _apply_basic_data(user: User, data: dict) -> None:
    user.name = data.get('name', user.name)
    user.gender = data.get('gender', user.gender)
    user.age = data.get('age', user.age)
    user.weight_kg = data.get('weight_kg', user.weight_kg)
    user.height_cm = data.get('height_cm', user.height_cm)
    user.body_fat_pct = data.get('body_fat_pct', user.body_fat_pct)


def _apply_goals(user: User, data: dict) -> None:
    user.goal_primary = data.get('goal_primary', user.goal_primary)
    user.goal_secondary = data.get('goal_secondary', user.goal_secondary)


def _apply_training_experience(user: User, data: dict) -> None:
    user.level = data.get('level', user.level)
    user.training_days_per_week = data.get('training_days_per_week', user.training_days_per_week)
    user.session_duration_min = data.get('session_duration_min', user.session_duration_min)
    user.equipment = data.get('equipment', user.equipment)


def _apply_physical_characteristics(user: User, data: dict) -> None:
    user.injuries_current = data.get('injuries_current', user.injuries_current)
    user.injuries_history = data.get('injuries_history', user.injuries_history)
    user.postural_issues = data.get('postural_issues', user.postural_issues)
    user.mobility_issues = data.get('mobility_issues', user.mobility_issues)
    user.muscle_imbalances = data.get('muscle_imbalances', user.muscle_imbalances)


def _apply_menstrual_cycle(user: User, data: dict) -> None:
    user.menstrual_tracking = data.get('menstrual_tracking', user.menstrual_tracking)
    user.cycle_length_days = data.get('cycle_length_days', user.cycle_length_days)
    if data.get('last_period_date'):
        from datetime import date
        user.last_period_date = date.fromisoformat(data['last_period_date'])


def _apply_training_style(user: User, data: dict) -> None:
    user.training_likes = data.get('training_likes', user.training_likes)
    user.training_dislikes = data.get('training_dislikes', user.training_dislikes)
    user.previous_methods = data.get('previous_methods', user.previous_methods)
    user.had_coach_before = data.get('had_coach_before', user.had_coach_before)


def _apply_psychology(user: User, data: dict) -> None:
    user.motivation_type = data.get('motivation_type', user.motivation_type)


def _apply_previous_program(user: User, data: dict) -> None:
    if data.get('previous_program_notes'):
        existing = user.training_likes or ''
        user.training_likes = existing + f"\nPrevious program: {data['previous_program_notes']}"


def _apply_body_measurements(user: User, data: dict) -> None:
    from datetime import date
    from app.core.models import BodyMeasurement
    m = BodyMeasurement(
        user_id=user.id, date=date.today(),
        weight_kg=data.get('weight_kg'),
        body_fat_pct=data.get('body_fat_pct'),
        waist_cm=data.get('waist_cm'),
        hips_cm=data.get('hips_cm'),
        chest_cm=data.get('chest_cm'),
        left_arm_cm=data.get('left_arm_cm'),
        right_arm_cm=data.get('right_arm_cm'),
        left_leg_cm=data.get('left_leg_cm'),
        right_leg_cm=data.get('right_leg_cm'),
    )
    db.session.add(m)
