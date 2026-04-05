from datetime import date, timedelta
from app.core.models import User, DailyCheckin
from app.modules.nutrition.models import NutritionProfile, MealLog


def build_nutrition_context(user_id: int) -> str:
    parts = ['\n## Nutrition Context']

    profile = NutritionProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        parts.append('Nutrition profile: not set up yet.')
    else:
        allergies_str = ', '.join(profile.allergies) if profile.allergies else 'none'
        parts.append(
            f'Diet: {profile.diet_type} | Allergies: {allergies_str} | '
            f'Skill: {profile.cooking_skill} | Budget: {profile.budget}'
        )
        parts.append(
            f'Targets: {profile.calorie_target} kcal | '
            f'Protein {profile.protein_g}g | Fat {profile.fat_g}g | Carbs {profile.carbs_g}g'
        )

    since = date.today() - timedelta(days=7)
    logs = (MealLog.query
            .filter(MealLog.user_id == user_id, MealLog.date >= since)
            .order_by(MealLog.date.desc())
            .limit(20)
            .all())
    if logs:
        parts.append('\nRecent meals (last 7 days):')
        for log in logs:
            parts.append(f'  {log.date}: {log.description}')
    else:
        parts.append('\nNo meals logged recently.')

    checkin = DailyCheckin.query.filter_by(user_id=user_id, date=date.today()).first()
    if checkin:
        parts.append(
            f'\nToday check-in: Energy {checkin.energy_level}/10, Sleep {checkin.sleep_quality}/10'
        )

    return '\n'.join(parts)
