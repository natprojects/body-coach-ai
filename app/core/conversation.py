from app.extensions import db
from app.core.models import AIConversation


def save_message(user_id: int, module: str, role: str, content: str) -> None:
    msg = AIConversation(user_id=user_id, module=module, role=role, content=content)
    db.session.add(msg)
    db.session.commit()


def load_conversation_window(user_id: int, module: str, limit: int = 15) -> list[dict]:
    messages = (
        AIConversation.query
        .filter_by(user_id=user_id, module=module)
        .filter(AIConversation.role.in_(['user', 'assistant']))
        .order_by(AIConversation.created_at.desc())
        .limit(limit)
        .all()
    )
    return [{'role': m.role, 'content': m.content} for m in reversed(messages)]
