from datetime import datetime

from flask import Response, g, jsonify, request, stream_with_context

from app.core.ai import get_client
from app.core.auth import require_auth
from app.extensions import db
from . import bp
from .context import COACH_SYSTEM, build_coach_context
from .models import ChatMessage, ChatThread


@bp.route('/coach/threads', methods=['GET'])
@require_auth
def list_threads():
    threads = (ChatThread.query
               .filter_by(user_id=g.user_id)
               .order_by(ChatThread.updated_at.desc())
               .all())
    return jsonify({'success': True, 'data': [
        {'id': t.id, 'title': t.title, 'updated_at': t.updated_at.isoformat()}
        for t in threads
    ]})


@bp.route('/coach/threads', methods=['POST'])
@require_auth
def create_thread():
    thread = ChatThread(user_id=g.user_id)
    db.session.add(thread)
    db.session.commit()
    return jsonify({'success': True, 'data': {'thread_id': thread.id}})


@bp.route('/coach/threads/<int:thread_id>', methods=['GET'])
@require_auth
def get_thread(thread_id):
    thread = ChatThread.query.filter_by(id=thread_id, user_id=g.user_id).first()
    if not thread:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Thread not found'}}), 404
    messages = (ChatMessage.query
                .filter_by(thread_id=thread_id)
                .order_by(ChatMessage.created_at)
                .limit(100)
                .all())
    return jsonify({'success': True, 'data': {
        'id': thread.id,
        'title': thread.title,
        'messages': [
            {'role': m.role, 'content': m.content, 'created_at': m.created_at.isoformat()}
            for m in messages
        ],
    }})


@bp.route('/coach/threads/<int:thread_id>', methods=['DELETE'])
@require_auth
def delete_thread(thread_id):
    thread = ChatThread.query.filter_by(id=thread_id, user_id=g.user_id).first()
    if not thread:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Thread not found'}}), 404
    db.session.delete(thread)
    db.session.commit()
    return jsonify({'success': True})


@bp.route('/coach/threads/<int:thread_id>/generate-title', methods=['POST'])
@require_auth
def generate_title(thread_id):
    thread = ChatThread.query.filter_by(id=thread_id, user_id=g.user_id).first()
    if not thread:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Thread not found'}}), 404
    first_msg = (ChatMessage.query
                 .filter_by(thread_id=thread_id, role='user')
                 .order_by(ChatMessage.created_at)
                 .first())
    if not first_msg:
        return jsonify({'success': True, 'data': {'title': thread.title}})
    from app.core.ai import complete
    raw = complete(
        'Generate a short conversation title (4-6 words, Ukrainian). Return ONLY the title, no punctuation, no quotes.',
        first_msg.content,
        max_tokens=30,
        model='claude-haiku-4-5-20251001',
    ).strip()
    thread.title = raw
    db.session.commit()
    return jsonify({'success': True, 'data': {'title': raw}})


@bp.route('/coach/threads/<int:thread_id>/chat', methods=['POST'])
@require_auth
def thread_chat(thread_id):
    thread = ChatThread.query.filter_by(id=thread_id, user_id=g.user_id).first()
    if not thread:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Thread not found'}}), 404

    data = request.json or {}
    user_message = (data.get('message') or '').strip()
    if not user_message:
        return jsonify({'success': False, 'error': {'code': 'EMPTY', 'message': 'Message required'}}), 400

    # Save user message
    user_msg = ChatMessage(thread_id=thread_id, role='user', content=user_message)
    db.session.add(user_msg)
    thread.updated_at = datetime.utcnow()
    db.session.commit()

    # Build conversation history (last 49 messages before this one)
    history_msgs = (ChatMessage.query
                    .filter(ChatMessage.thread_id == thread_id,
                            ChatMessage.id != user_msg.id)
                    .order_by(ChatMessage.created_at.desc())
                    .limit(49)
                    .all())[::-1]
    messages = [{'role': m.role, 'content': m.content} for m in history_msgs]
    messages.append({'role': 'user', 'content': user_message})

    system = COACH_SYSTEM + '\n\n' + build_coach_context(g.user_id)

    # Collect AI response synchronously so the assistant message is saved
    # before the HTTP response is returned (required for testability and
    # to avoid context lifecycle issues with stream_with_context).
    chunks = []
    with get_client().messages.stream(
        model='claude-sonnet-4-6',
        max_tokens=2048,
        system=system,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            chunks.append(text)

    ai_content = ''.join(chunks)
    ai_msg = ChatMessage(thread_id=thread_id, role='assistant', content=ai_content)
    db.session.add(ai_msg)
    thread.updated_at = datetime.utcnow()
    db.session.commit()

    def generate():
        for chunk in chunks:
            yield f'data: {chunk}\n\n'
        yield 'data: [DONE]\n\n'

    return Response(generate(), mimetype='text/event-stream')
