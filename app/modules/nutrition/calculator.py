BASE_FACTORS = {
    'sedentary':  1.20,
    'lightly':    1.375,
    'moderately': 1.55,
    'very':       1.725,
}

GOAL_ADJUSTMENTS = {
    'fat_loss':    -400,
    'hypertrophy': +250,
    'strength':    +250,
}


def _training_bonus(training_days_per_week: int) -> float:
    if training_days_per_week <= 1:
        return 0.0
    elif training_days_per_week <= 3:
        return 0.10
    elif training_days_per_week <= 5:
        return 0.175
    else:
        return 0.25


def calc_bmr(weight_kg: float, height_cm: float, age: int, gender: str) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base - 161 if gender == 'female' else base + 5


def calc_tdee(bmr: float, activity_outside: str, training_days_per_week: int) -> float:
    if activity_outside not in BASE_FACTORS:
        raise ValueError(f"Unknown activity_outside: {activity_outside!r}")
    base = BASE_FACTORS[activity_outside]
    bonus = _training_bonus(training_days_per_week)
    return bmr * (base + bonus)


def calc_calorie_target(tdee: float, goal_primary: str) -> float:
    return tdee + GOAL_ADJUSTMENTS.get(goal_primary, 0)


def calc_macros(weight_kg: float, calorie_target: float) -> dict:
    protein_g = round(2.0 * weight_kg, 1)
    fat_g     = round(calorie_target * 0.28 / 9, 1)
    carbs_g   = round((calorie_target - protein_g * 4 - fat_g * 9) / 4, 1)
    carbs_g   = max(0.0, carbs_g)
    return {'protein_g': protein_g, 'fat_g': fat_g, 'carbs_g': carbs_g}


def calc_water_ml(weight_kg: float) -> int:
    return round(weight_kg * 32.5)
