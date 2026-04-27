"""Calisthenics program generation: AI prompt + save."""
import json
import re
from app.core.ai import complete
from app.extensions import db
from app.modules.training.models import (
    Program, Mesocycle, ProgramWeek, Workout, Exercise, WorkoutExercise, PlannedSet,
)
from .models import CalisthenicsProfile, CalisthenicsAssessment


def _calisthenics_exercise_catalog() -> list:
    """Return seeded calisthenics exercises as a list of dicts for the AI prompt."""
    rows = (Exercise.query
            .filter_by(module='calisthenics')
            .order_by(Exercise.progression_chain, Exercise.progression_level)
            .all())
    return [
        {'name': r.name, 'chain': r.progression_chain,
         'level': r.progression_level, 'unit': r.unit}
        for r in rows
    ]


def _resolve_calisthenics_exercise(name: str) -> Exercise:
    """Resolve an AI-returned exercise name to a seeded Exercise row. Raises on unknown."""
    cleaned = (name or '').strip().lower()
    ex = Exercise.query.filter_by(module='calisthenics', name=cleaned).first()
    if not ex:
        # try with original casing
        ex = Exercise.query.filter_by(module='calisthenics', name=name.strip()).first()
    if not ex:
        raise ValueError(f"Unknown calisthenics exercise: {name!r}")
    return ex


def generate_calisthenics_program(user, profile: CalisthenicsProfile,
                                   last_assessment: CalisthenicsAssessment) -> dict:
    """Call Claude to generate a calisthenics program. Returns parsed JSON dict."""
    catalog = _calisthenics_exercise_catalog()
    days = profile.days_per_week or 3
    duration = profile.session_duration_min or 45

    system_prompt = f"""You are an expert calisthenics coach.
Generate a calisthenics training program as compact JSON only — no prose, no markdown, just valid JSON.

STRICT OUTPUT CONSTRAINTS:
- Exactly 1 mesocycle
- Exactly 1 week inside that mesocycle (week_number: 1) — repeating template
- Exactly {days} workouts in that week (one per training day, day_of_week 0..6)
- 4-6 exercises per workout (compound first)
- Exactly 3 sets per exercise; the LAST set MUST have is_amrap: true, others false

CLOSED EXERCISE LIST (use ONLY these names, exactly as written):
{json.dumps(catalog, ensure_ascii=False)}

LEVEL SELECTION HEURISTICS based on the user's assessment:
- pushups <5 → pick push level 1-2; 5-12 → level 3; 13-25 → level 4; 25+ → level 5+
- pullups null or 0 → pick pull level 0-2 only; 1-3 → level 3-4; 4-8 → level 5; 8+ → 6+
- if pullups is null OR equipment lacks pullup_bar/dip_bars/rings → SKIP pull chain entirely; use only push/squat/core/lunge
- squats <15 → squat level 0-1; 15-30 → level 2-3; 30+ → 4
- plank seconds <30 → core_static level 0-1; 30-60 → 2; 60+ → 3
- hollow_body seconds <20 → start at core_static 1; 20-45 → 2; 45+ → 3
- lunges <10 → lunge level 0; 10-20 → 1; 20+ → 2

INJURIES:
- knees → no jumping lunge, no pistol squat
- wrists → skip diamond pushup level 4
- shoulders → no decline pushup, no archer pushup
- back → no dragon flag negative

PROGRAM STRUCTURE REQUIREMENTS:
- Program name in English (e.g. "Calisthenics Foundations", "Push-Pull Builder")
- periodization_type: "hypertrophy" or "skill"
- total_weeks: 4 (beginner) | 5 (intermediate) | 6 (advanced)
- For each set: target_reps as string range "8-12", or target_seconds as integer for seconds-unit exercises (target_reps null in that case)
- target_rpe 7-9, rest_seconds 60-120
- tempo "3-1-2-0" format
- coaching_notes brief"""

    user_prompt = f"""Create a calisthenics program for:
- Name: {user.name}, Gender: {user.gender}, Age: {user.age}, Level: {user.level}
- Goals: {profile.goals}, Equipment: {profile.equipment}, Injuries: {profile.injuries}
- Sessions: {days}/week × {duration} min, Motivation: {profile.motivation}

Last assessment:
- pullups: {last_assessment.pullups}, australian_pullups: {last_assessment.australian_pullups}
- pushups: {last_assessment.pushups}, pike_pushups: {last_assessment.pike_pushups}
- squats: {last_assessment.squats}, lunges: {last_assessment.lunges}
- plank: {last_assessment.plank}s, hollow_body: {last_assessment.hollow_body}s, superman_hold: {last_assessment.superman_hold}s

JSON structure:
{{"name":"...","periodization_type":"hypertrophy","total_weeks":4,"mesocycles":[{{"name":"Block 1","order_index":0,"weeks_count":1,"weeks":[{{"week_number":1,"notes":null,"workouts":[{{"day_of_week":0,"name":"Push A","order_index":0,"target_muscle_groups":"Chest, Triceps","estimated_duration_min":35,"warmup_notes":"...","exercises":[{{"exercise_name":"full pushup","order_index":0,"tempo":"3-1-2-0","is_mandatory":true,"coaching_notes":"...","sets":[{{"set_number":1,"target_reps":"8-12","target_seconds":null,"target_rpe":7.0,"rest_seconds":90,"is_amrap":false}},{{"set_number":2,"target_reps":"8-12","target_seconds":null,"target_rpe":8.0,"rest_seconds":90,"is_amrap":false}},{{"set_number":3,"target_reps":"8-12","target_seconds":null,"target_rpe":9.0,"rest_seconds":90,"is_amrap":true}}]}}]}}]}}]}}]}}

Use day_of_week 0=Mon..6=Sun."""

    raw = complete(system_prompt=system_prompt, user_message=user_prompt,
                   max_tokens=4096, model='claude-sonnet-4-6')
    # Strip markdown code fences that the model sometimes wraps around JSON
    raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI returned invalid JSON: {e}") from e


def save_calisthenics_program_from_dict(user_id: int, program_dict: dict) -> Program:
    """Persist a generated program; archive any prior active calisthenics program."""
    # Archive previous active calisthenics program(s)
    prior = Program.query.filter_by(
        user_id=user_id, module='calisthenics', status='active'
    ).all()
    for p in prior:
        p.status = 'completed'

    program = Program(
        user_id=user_id,
        name=program_dict['name'],
        periodization_type=program_dict.get('periodization_type', 'hypertrophy'),
        total_weeks=program_dict.get('total_weeks', 4),
        status='active',
        module='calisthenics',
    )
    db.session.add(program)
    db.session.flush()

    for m_dict in program_dict.get('mesocycles', []):
        meso = Mesocycle(
            program_id=program.id,
            name=m_dict['name'],
            order_index=m_dict.get('order_index', 0),
            weeks_count=m_dict.get('weeks_count', 1),
        )
        db.session.add(meso)
        db.session.flush()

        for w_dict in m_dict.get('weeks', []):
            week = ProgramWeek(
                mesocycle_id=meso.id,
                week_number=w_dict['week_number'],
                notes=w_dict.get('notes'),
            )
            db.session.add(week)
            db.session.flush()

            for wo_dict in w_dict.get('workouts', []):
                workout = Workout(
                    program_week_id=week.id,
                    day_of_week=wo_dict['day_of_week'],
                    name=wo_dict['name'],
                    order_index=wo_dict.get('order_index', 0),
                    target_muscle_groups=wo_dict.get('target_muscle_groups'),
                    estimated_duration_min=wo_dict.get('estimated_duration_min'),
                    warmup_notes=wo_dict.get('warmup_notes'),
                )
                db.session.add(workout)
                db.session.flush()

                for ex_dict in wo_dict.get('exercises', []):
                    exercise = _resolve_calisthenics_exercise(ex_dict['exercise_name'])
                    we = WorkoutExercise(
                        workout_id=workout.id,
                        exercise_id=exercise.id,
                        order_index=ex_dict.get('order_index', 0),
                        tempo=ex_dict.get('tempo'),
                        is_mandatory=ex_dict.get('is_mandatory', True),
                        notes=ex_dict.get('coaching_notes') or ex_dict.get('notes'),
                    )
                    db.session.add(we)
                    db.session.flush()

                    for s_dict in ex_dict.get('sets', []):
                        ps = PlannedSet(
                            workout_exercise_id=we.id,
                            set_number=s_dict['set_number'],
                            target_reps=s_dict.get('target_reps'),
                            target_seconds=s_dict.get('target_seconds'),
                            target_weight_kg=None,
                            target_rpe=s_dict.get('target_rpe'),
                            rest_seconds=s_dict.get('rest_seconds'),
                            is_amrap=s_dict.get('is_amrap', False),
                        )
                        db.session.add(ps)

    db.session.commit()
    return program


_VALID_MINI_TYPES = {'stretch', 'short', 'skill'}


def save_mini_session_from_dict(user_id: int, mini_type: str, mini_dict: dict) -> Workout:
    """Persist an AI-generated mini-session as a Workout row with program_week_id=NULL.
    Reuses existing WorkoutExercise/PlannedSet hierarchy so logging is identical to main."""
    if mini_type not in _VALID_MINI_TYPES:
        raise ValueError(f"Invalid mini_type: {mini_type!r}")

    workout = Workout(
        program_week_id=None,
        mini_kind=mini_type,
        user_id=user_id,  # ownership for mini-workouts
        day_of_week=0,
        name=mini_dict.get('name', f'{mini_type} session'),
        order_index=0,
        estimated_duration_min=mini_dict.get('estimated_duration_min'),
        warmup_notes=mini_dict.get('warmup_notes'),
    )
    db.session.add(workout)
    db.session.flush()

    for ex_dict in mini_dict.get('exercises', []):
        exercise = _resolve_calisthenics_exercise(ex_dict['exercise_name'])
        we = WorkoutExercise(
            workout_id=workout.id,
            exercise_id=exercise.id,
            order_index=ex_dict.get('order_index', 0),
            tempo=ex_dict.get('tempo'),
            is_mandatory=ex_dict.get('is_mandatory', True),
            notes=ex_dict.get('coaching_notes') or ex_dict.get('notes'),
        )
        db.session.add(we)
        db.session.flush()

        for s_dict in ex_dict.get('sets', []):
            ps = PlannedSet(
                workout_exercise_id=we.id,
                set_number=s_dict['set_number'],
                target_reps=s_dict.get('target_reps'),
                target_seconds=s_dict.get('target_seconds'),
                target_weight_kg=None,
                target_rpe=s_dict.get('target_rpe'),
                rest_seconds=s_dict.get('rest_seconds'),
                is_amrap=s_dict.get('is_amrap', False),
            )
            db.session.add(ps)

    db.session.commit()
    return workout


_MINI_PROMPTS = {
    'stretch': {
        'duration_min': 10,
        'guidance': (
            "Generate a 10-minute mobility / stretch session with 5-7 exercises, "
            "30-60 seconds each. Target: hips, shoulders, spine, posture. "
            "All exercises are seconds-based (target_seconds set, target_reps null). "
            "No AMRAP. Anchor selections to user's injuries (avoid aggravating positions)."
        ),
    },
    'short': {
        'duration_min': 15,
        'guidance': (
            "Generate a 15-minute compact strength session with 3-4 exercises, "
            "2 sets each. The LAST set of each exercise has is_amrap: true. "
            "Use exercise levels matching the user's main program — don't push harder. "
            "Avoid duplicating chains the user already trained today (a comma-separated list "
            "of recently used chains is provided as 'today_main_chains')."
        ),
    },
    'skill': {
        'duration_min': 10,
        'guidance': (
            "Generate a 10-minute skill-focus session with 1-2 specific skill progressions. "
            "Examples: L-sit holds, handstand wall holds, planche leans, dragon flag negatives. "
            "Focus on form/quality, low volume (3-4 sets × 5-15s holds OR 3 reps with 60-90s rest). "
            "Pick a skill the user is close to but hasn't fully mastered, looking at their assessment."
        ),
    },
}


def generate_mini_session(user, profile: CalisthenicsProfile,
                          last_assessment: CalisthenicsAssessment, mini_type: str,
                          today_main_chains: list = None) -> dict:
    """Call Claude to generate a mini-session of the given type. Returns parsed JSON dict."""
    if mini_type not in _VALID_MINI_TYPES:
        raise ValueError(f"Invalid mini_type: {mini_type!r}")

    config = _MINI_PROMPTS[mini_type]
    catalog = _calisthenics_exercise_catalog()

    system_prompt = f"""You are an expert calisthenics coach.
Generate a calisthenics MINI-SESSION as compact JSON only — no prose, no markdown, just valid JSON.

{config['guidance']}

CLOSED EXERCISE LIST (use ONLY these names, exactly as written):
{json.dumps(catalog, ensure_ascii=False)}

INJURIES from profile: {profile.injuries or []}
GOALS: {profile.goals or []}

JSON shape (compact):
{{"name":"...","estimated_duration_min":{config['duration_min']},"warmup_notes":"...","exercises":[{{"exercise_name":"...","order_index":0,"tempo":"...","is_mandatory":true,"coaching_notes":"...","sets":[{{"set_number":1,"target_reps":"8-12","target_seconds":null,"target_rpe":7.0,"rest_seconds":60,"is_amrap":false}}]}}]}}"""

    user_prompt = f"""User: {user.name}, level: {user.level}, equipment: {profile.equipment}
Last assessment: pushups={last_assessment.pushups}, pullups={last_assessment.pullups}, squats={last_assessment.squats}, plank={last_assessment.plank}s, hollow={last_assessment.hollow_body}s
today_main_chains: {today_main_chains or []}

Return only the JSON object."""

    response = complete(
        system_prompt=system_prompt, user_message=user_prompt,
        max_tokens=2048, model='claude-sonnet-4-6',
    )
    response = re.sub(r'^```(?:json)?\s*', '', response.strip())
    response = re.sub(r'\s*```$', '', response).strip()
    try:
        return json.loads(response)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI returned invalid JSON for mini-session: {e}")


def generate_calisthenics_insights(program, user, profile, last_assessment) -> int:
    """Generate selection_reason + expected_outcome for every WorkoutExercise in a calisthenics
    program. Returns count of exercises updated."""
    wes = (WorkoutExercise.query
           .join(Workout)
           .join(ProgramWeek)
           .join(Mesocycle)
           .filter(Mesocycle.program_id == program.id)
           .order_by(Mesocycle.order_index, ProgramWeek.week_number,
                     Workout.order_index, WorkoutExercise.order_index)
           .all())

    if not wes:
        return 0

    exercises_data = []
    for we in wes:
        ex = db.session.get(Exercise, we.exercise_id)
        exercises_data.append({
            'workout_exercise_id': we.id,
            'exercise_name': ex.name,
            'progression_chain': ex.progression_chain,
            'progression_level': ex.progression_level,
            'unit': ex.unit,
            'workout_name': we.workout.name,
            'day_of_week': we.workout.day_of_week,
        })

    lang = getattr(user, 'app_language', None) or 'uk'
    lang_instruction = " Write all text fields in Ukrainian." if lang == 'uk' else ""

    system_prompt = (
        "You are an expert calisthenics coach. "
        "Return a JSON array only — no prose, no markdown fences. "
        "For each exercise explain why it was chosen for this specific user (consider their "
        "assessment scores, goals, equipment, injuries, and where it sits in its progression chain), "
        "and what outcome to expect after a few weeks of consistent training. "
        "Keep each field 1-3 sentences, conversational tone. "
        f"Return exactly one object per input exercise, in the same order.{lang_instruction}"
    )

    profile_summary = (
        f"Goals: {profile.goals}, Equipment: {profile.equipment}, Injuries: {profile.injuries}, "
        f"Days/week: {profile.days_per_week}, Session: {profile.session_duration_min} min, "
        f"Motivation: {profile.motivation}"
    )
    assessment_summary = (
        f"pullups: {last_assessment.pullups}, australian_pullups: {last_assessment.australian_pullups}, "
        f"pushups: {last_assessment.pushups}, pike_pushups: {last_assessment.pike_pushups}, "
        f"squats: {last_assessment.squats}, lunges: {last_assessment.lunges}, "
        f"plank: {last_assessment.plank}s, hollow_body: {last_assessment.hollow_body}s, "
        f"superman_hold: {last_assessment.superman_hold}s"
    )

    user_prompt = (
        f"User profile (calisthenics):\n"
        f"- Name: {user.name}, Gender: {user.gender}, Age: {user.age}, Level: {user.level}\n"
        f"- {profile_summary}\n\n"
        f"Last assessment: {assessment_summary}\n\n"
        f"Program: {program.name} ({program.total_weeks} weeks, {program.periodization_type})\n\n"
        f"Exercises:\n{json.dumps(exercises_data, ensure_ascii=False)}\n\n"
        "Return JSON array with fields: workout_exercise_id, selection_reason, expected_outcome"
    )

    raw = complete(system_prompt, user_prompt, max_tokens=8192, model='claude-sonnet-4-6')
    raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw).strip()

    insights = json.loads(raw)

    we_map = {we.id: we for we in wes}
    for item in insights:
        we = we_map.get(item.get('workout_exercise_id'))
        if we:
            we.selection_reason = item.get('selection_reason')
            we.expected_outcome = item.get('expected_outcome')

    db.session.commit()
    return len(insights)
