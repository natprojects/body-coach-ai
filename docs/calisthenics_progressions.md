# Calisthenics Progression Chains

Closed list of progression exercises seeded into the `exercises` table by migration `h8i9j0k1l2m3`. The AI generation prompt in `app/modules/calisthenics/coach.py` references these by name — adding a new exercise requires both seeding it via migration and adjusting the AI prompt's level heuristics if needed.

## Push (10 levels)
0. wall pushup — feet stand-distance from wall, hands shoulder-width
1. incline pushup — hands on bench/chair, body angled
2. knee pushup — knees on floor, full ROM
3. full pushup — feet on floor, hands shoulder-width
4. diamond pushup — hands together forming diamond
5. decline pushup — feet elevated
6. archer pushup — one arm bent, other straight
7. pseudo planche pushup — hands at hips, lean forward
8. one-arm pushup negative — slow eccentric only
9. one-arm pushup — full ROM

## Pull (8 levels) — requires pullup bar / dip bars / rings
0. dead hang (seconds)
1. scapular pull
2. australian pullup — body horizontal under bar
3. negative pullup — slow lowering only
4. band-assisted pullup
5. full pullup
6. archer pullup
7. one-arm pullup negative

## Squat (5 levels)
0. assisted squat — holding support
1. full bodyweight squat
2. bulgarian split squat — back foot elevated
3. pistol squat negative
4. pistol squat — full single-leg

## Core dynamic (5 levels)
0. dead bug
1. hanging knee raise — requires bar
2. hanging leg raise — requires bar
3. toes-to-bar — requires bar
4. dragon flag negative

## Core static (5 levels, all in seconds)
0. forearm plank
1. hollow body hold
2. l-sit tuck
3. l-sit
4. v-sit progression

## Lunge (4 levels)
0. reverse lunge
1. walking lunge
2. jumping lunge
3. shrimp squat regression

## Promotion criteria
Computed by `compute_level_up_suggestions()` in `app/modules/calisthenics/level_up.py`. After every completed session, for each exercise in the active program:

- Look at the user's last 3 completed sessions that included this exercise
- Find the AMRAP (highest set_number) logged value in each
- Reps: AMRAP value ≥ `target_reps_upper_bound + 3` for all 3 sessions
- Seconds: AMRAP value ≥ `target_seconds + 10` for all 3 sessions

If passed and a next exercise exists in the same chain, the system suggests the promotion. The user confirms via `POST /api/calisthenics/program/<id>/level-up` which:
1. Re-validates the criterion server-side (rejects with `LEVEL_UP_NOT_READY` if stale)
2. Swaps `WorkoutExercise.exercise_id` everywhere this exercise appears in the program
3. Rescales `PlannedSet` targets to start of next level's range (`6-10` reps or `target_seconds - 10`)

## Equipment requirements
- pull chain → requires one of: `pullup_bar`, `dip_bars`, `rings`
- core_dynamic levels 1-3 → requires bar
- core_dynamic level 4 → no equipment needed
- pseudo planche, one-arm progressions (push 7-9) → require sturdy floor; skip if user has wrist injury

## Injury contraindications (encoded in AI prompt)
- knees → no jumping lunge, no pistol squat
- wrists → skip diamond pushup
- shoulders → no decline pushup, no archer pushup
- back → no dragon flag negative
