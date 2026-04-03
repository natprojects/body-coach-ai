# app/modules/training/cycle.py
from datetime import date
from app.core.models import DailyCheckin, User
from app.extensions import db

PHASE_DATA = {
    'menstrual': {
        'title': 'Менструальна фаза',
        'description': 'Тренуйся за самопочуттям. Якщо енергія низька — не форсуй.',
        'modifier': 1.0,
        'pr_allowed': True,
        'warnings': [],
    },
    'follicular': {
        'title': 'Фолікулярна фаза',
        'description': 'Найкращий час для важких тренувань і нових рекордів.',
        'modifier': 1.0,
        'pr_allowed': True,
        'warnings': [],
    },
    'ovulation': {
        'title': 'Овуляція',
        'description': "Підвищена лаксичність зв'язок. Зроби додаткову розминку суглобів, уникай стрибків.",
        'modifier': 1.0,
        'pr_allowed': True,
        'warnings': ["Уникай плайометрики (стрибки, бурпі) — підвищений ризик травми зв'язок."],
    },
    'luteal': {
        'title': 'Лютеальна фаза',
        'description': 'Знижена працездатність — це нормально. −10% ваги, без рекордів. Фокус на техніку.',
        'modifier': 0.9,
        'pr_allowed': False,
        'warnings': [],
    },
}

_PLYOMETRIC_KW = ('jump', 'box jump', 'burpee', 'hop', 'bound', 'стрибок', 'бурпі', 'lunge jump')
_COMPOUND_KW = ('squat', 'deadlift', 'bench press', 'overhead press', 'military press',
                'rdl', 'romanian', 'row', 'присід', 'мертва', 'жим')


def _is_plyometric(name: str) -> bool:
    n = name.lower()
    return any(kw in n for kw in _PLYOMETRIC_KW)


def _is_compound(name: str) -> bool:
    n = name.lower()
    return any(kw in n for kw in _COMPOUND_KW)


def _phase_for_day(cycle_day: int) -> str:
    if cycle_day <= 5:
        return 'menstrual'
    if cycle_day <= 11:
        return 'follicular'
    if cycle_day <= 16:
        return 'ovulation'
    return 'luteal'


def get_cycle_phase(user_id: int) -> dict:
    """Return cycle phase info for the user.

    Returns {'show_card': False} if cycle tracking is not enabled or data is missing.
    """
    user = db.session.get(User, user_id)
    if not user or not user.menstrual_tracking or not user.last_period_date:
        return {'show_card': False}

    today_checkin = DailyCheckin.query.filter_by(
        user_id=user_id, date=date.today()
    ).first()

    if today_checkin and today_checkin.cycle_day:
        cycle_day = today_checkin.cycle_day
    else:
        cycle_length = user.cycle_length_days or 28
        days_since = (date.today() - user.last_period_date).days
        cycle_day = (days_since % cycle_length) + 1

    phase = _phase_for_day(cycle_day)
    info = dict(PHASE_DATA[phase])
    info['warnings'] = list(info['warnings'])

    # Determine whether to show the pre-workout card
    if phase == 'follicular':
        show_card = False
    elif phase == 'menstrual':
        energy = getattr(today_checkin, 'energy_level', None) if today_checkin else None
        show_card = bool(energy and energy < 5)
    else:
        show_card = True  # ovulation and luteal always show card

    return {
        'show_card': show_card,
        'phase': phase,
        'cycle_day': cycle_day,
        'modifier': info['modifier'],
        'phase_title': info['title'],
        'phase_description': info['description'],
        'warnings': info['warnings'],
        'pr_allowed': info['pr_allowed'],
    }
