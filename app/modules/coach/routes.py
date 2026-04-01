from datetime import datetime

from flask import Response, g, jsonify, request, stream_with_context

from app.core.auth import require_auth
from app.extensions import db
from . import bp
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
