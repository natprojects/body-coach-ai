import pytest
from app.modules.nutrition.calculator import (
    calc_bmr, calc_tdee, calc_calorie_target, calc_macros, calc_water_ml
)


def test_bmr_female():
    # 10*60 + 6.25*165 - 5*25 - 161 = 600 + 1031.25 - 125 - 161 = 1345.25
    assert calc_bmr(60.0, 165.0, 25, 'female') == pytest.approx(1345.25, abs=0.1)


def test_bmr_male():
    # 10*80 + 6.25*180 - 5*30 + 5 = 800 + 1125 - 150 + 5 = 1780
    assert calc_bmr(80.0, 180.0, 30, 'male') == pytest.approx(1780.0, abs=0.1)


def test_tdee_sedentary_no_training():
    # 1400 * (1.2 + 0.0) = 1680
    assert calc_tdee(1400.0, 'sedentary', 0) == pytest.approx(1680.0, abs=0.1)


def test_tdee_lightly_3_days():
    # 1400 * (1.375 + 0.10) = 1400 * 1.475 = 2065
    assert calc_tdee(1400.0, 'lightly', 3) == pytest.approx(2065.0, abs=0.1)


def test_tdee_moderately_5_days():
    # 1400 * (1.55 + 0.175) = 1400 * 1.725 = 2415
    assert calc_tdee(1400.0, 'moderately', 5) == pytest.approx(2415.0, abs=0.1)


def test_tdee_very_7_days():
    # 1400 * (1.725 + 0.25) = 1400 * 1.975 = 2765
    assert calc_tdee(1400.0, 'very', 7) == pytest.approx(2765.0, abs=0.1)


def test_calorie_target_fat_loss():
    assert calc_calorie_target(2000.0, 'fat_loss') == pytest.approx(1600.0)


def test_calorie_target_hypertrophy():
    assert calc_calorie_target(2000.0, 'hypertrophy') == pytest.approx(2250.0)


def test_calorie_target_strength():
    assert calc_calorie_target(2000.0, 'strength') == pytest.approx(2250.0)


def test_calorie_target_maintenance():
    assert calc_calorie_target(2000.0, 'general_fitness') == pytest.approx(2000.0)


def test_macros_standard():
    # weight=66kg, calories=2000
    # protein = 2.0 * 66 = 132g
    # fat = 2000 * 0.28 / 9 ≈ 62.2g
    # carbs = (2000 - 132*4 - 62.2*9) / 4 > 0
    result = calc_macros(66.0, 2000.0)
    assert result['protein_g'] == 132.0
    assert result['fat_g'] == pytest.approx(62.2, abs=0.5)
    assert result['carbs_g'] > 0


def test_macros_no_negative_carbs():
    # very high body weight, low calories → carbs clamped to 0
    result = calc_macros(120.0, 1200.0)
    assert result['carbs_g'] == 0.0


def test_water_ml():
    assert calc_water_ml(60.0) == 1950.0   # 60 * 32.5
    assert calc_water_ml(80.0) == 2600.0   # 80 * 32.5
