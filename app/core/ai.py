import anthropic
from datetime import date
from flask import current_app

from app.core.conversation import load_conversation_window, save_message
from app.core.models import DailyCheckin, User
from app.extensions import db

_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=current_app.config['ANTHROPIC_API_KEY'])
    return _client


def build_base_system(user_id: int) -> str:
    user = db.session.get(User, user_id)
    parts = [
        "You are a professional AI body coach — personal, evidence-based, and motivating.",
        "\n## User Profile",
        f"Name: {user.name}, Gender: {user.gender}, Age: {user.age}",
        f"Weight: {user.weight_kg}kg, Height: {user.height_cm}cm"
        + (f", Body fat: {user.body_fat_pct}%" if user.body_fat_pct else ""),
        f"Primary goal: {user.goal_primary}, Level: {user.level}",
        f"Training: {user.training_days_per_week} days/week, {user.session_duration_min} min/session",
        f"Equipment: {user.equipment}",
    ]
    if user.injuries_current:
        parts.append(f"Current injuries: {user.injuries_current}")
    if user.postural_issues:
        parts.append(f"Postural issues: {user.postural_issues}")
    if user.mobility_issues:
        parts.append(f"Mobility restrictions: {user.mobility_issues}")

    checkin = DailyCheckin.query.filter_by(user_id=user_id, date=date.today()).first()
    if checkin:
        parts += [
            "\n## Today's Check-in",
            f"Energy: {checkin.energy_level}/10, Sleep: {checkin.sleep_quality}/10",
            f"Stress: {checkin.stress_level}/10, Motivation: {checkin.motivation}/10",
            f"Soreness: {checkin.soreness_level}/10",
        ]
        if checkin.notes:
            parts.append(f"Notes: {checkin.notes}")

    return '\n'.join(parts)


def stream_chat(user_id: int, module: str, user_message: str, extra_context: str = ""):
    """Generator that yields text chunks. Saves messages to conversation history."""
    system = build_base_system(user_id)
    if extra_context:
        system += f"\n\n{extra_context}"

    window_size = current_app.config.get('CONVERSATION_WINDOW_SIZE', 15)
    history = load_conversation_window(user_id, module, limit=window_size)
    messages = history + [{"role": "user", "content": user_message}]

    save_message(user_id, module, 'user', user_message)

    full_response = []
    with get_client().messages.stream(
        model=current_app.config['AI_MODEL'],
        max_tokens=2048,
        system=system,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            full_response.append(text)
            yield text

    save_message(user_id, module, 'assistant', ''.join(full_response))


def complete(system_prompt: str, user_message: str, max_tokens: int = 4096) -> str:
    """Non-streaming completion for structured outputs (program gen, reports)."""
    response = get_client().messages.create(
        model=current_app.config['AI_MODEL'],
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text
