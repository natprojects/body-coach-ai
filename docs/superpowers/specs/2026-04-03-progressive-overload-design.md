# Progressive Overload — Design Spec (v1.4)

**Goal:** Automatic load progression system that goes beyond weight increases.

---

## Progression Methods (priority order)

1. Збільшення ваги (+2.5кг верх тіла, +5кг ноги)
2. Збільшення повторів (в межах діапазону)
3. Збільшення підходів
4. Сповільнення темпу (більше time under tension)
5. Зменшення відпочинку
6. Збільшення амплітуди
7. Покращення техніки (теж прогрес)

---

## Decision Tree

| Condition | Action |
|-----------|--------|
| Всі підходи на максимальних повторах, RPE ≤ 8 | Збільшити вагу |
| Всі підходи в діапазоні, RPE 7–8 | Збільшити повтори |
| RPE 9–10, не всі повтори виконані | Тримати поточну вагу |
| Стагнація 3+ тижні | AI пропонує зміну стратегії (інша варіація, схема повторів, тип прогресії) |
| RPE 9–10 + біль | Зменшити або замінити вправу |
| Deload тиждень | 60% від робочої ваги, менше підходів |

---

## Periodization by Level

| Level | Type | Description |
|-------|------|-------------|
| Beginner | Linear | Щоразу більше (кожне тренування) |
| Intermediate | Wave | Легкий → Середній → Важкий тижні |
| Advanced | Block | Акумуляція → Інтенсифікація → Піковий → Deload |

---

## Deload Protocol

- **Frequency:** Кожні 4–6 тижнів (залежно від рівня)
- **Auto-detection:**
  - Стагнація 60%+ вправ, АБО
  - Хронічно поганий чекін 5+ днів поспіль
- **Protocol:** Об'єм −50%, інтенсивність зберігається
- **Duration:** 1 тиждень

---

## Current Implementation Status

### Implemented ✓
- `ExerciseRecommendation` model (weight/reps recommendations)
- `analyze_session_and_recommend()` — basic weight/rep progression
- `check_deload_needed()` — stagnation + check-in detection
- `GET /api/training/recommendations/today` — today's targets
- Frontend: TODAY'S TARGETS + inline feedback + NEXT SESSION PLAN

### To Implement
- Multi-method progression (sets, tempo, rest, ROM, technique)
- Full RPE-based decision tree (currently partial)
- Stagnation 3+ weeks → AI strategy change suggestion
- RPE 9-10 + pain → reduce/replace recommendation
- Periodization-aware progression (linear vs wave vs block)
- Deload protocol: volume −50%, intensity maintained
- Deload weight targets in NEXT SESSION PLAN
