from datetime import datetime

from flask import Response, g, jsonify, request, stream_with_context

from app.core.ai import get_client
from app.core.auth import require_auth
from app.extensions import db
from . import bp
from .context import (
    COACH_SYSTEM,
    NUTRITIONIST_SYSTEM_ADDENDUM,
    build_coach_context,
    build_cross_thread_history,
)
from .models import ChatMessage, ChatThread


@bp.route('/coach/threads', methods=['GET'])
@require_auth
def list_threads():
    threads = (ChatThread.query
               .filter_by(user_id=g.user_id)
               .order_by(ChatThread.updated_at.desc())
               .all())
    return jsonify({'success': True, 'data': [
        {'id': t.id, 'title': t.title, 'system_role': t.system_role,
         'updated_at': t.updated_at.isoformat()}
        for t in threads
    ]})


@bp.route('/coach/threads', methods=['POST'])
@require_auth
def create_thread():
    data = request.json or {}
    role = data.get('system_role')
    if role and role not in ('nutritionist',):
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_ROLE', 'message': f'Unknown system_role: {role}',
        }}), 400
    title = data.get('title') or ('🥗 Нутриціолог' if role == 'nutritionist' else 'Нова розмова')
    thread = ChatThread(user_id=g.user_id, system_role=role, title=title)
    db.session.add(thread)
    db.session.commit()
    return jsonify({'success': True, 'data': {
        'thread_id': thread.id,
        'title': thread.title,
        'system_role': thread.system_role,
    }})


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
        'system_role': thread.system_role,
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

    system = COACH_SYSTEM
    if thread.system_role == 'nutritionist':
        system += NUTRITIONIST_SYSTEM_ADDENDUM
    system += '\n\n' + build_coach_context(g.user_id)
    cross_history = build_cross_thread_history(g.user_id, thread_id)
    if cross_history:
        system += '\n\n' + cross_history

    def generate():
        full_response = []
        with get_client().messages.stream(
            model='claude-sonnet-4-6',
            max_tokens=2048,
            system=system,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                full_response.append(text)
                yield f"data: {text.replace(chr(10), ' ')}\n\n"

        ai_content = ''.join(full_response)
        ai_msg = ChatMessage(thread_id=thread_id, role='assistant', content=ai_content)
        db.session.add(ai_msg)
        thread.updated_at = datetime.utcnow()
        db.session.commit()

        yield 'data: [DONE]\n\n'

    return Response(stream_with_context(generate()), mimetype='text/event-stream')
