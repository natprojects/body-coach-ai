from app.core.models import User
from app.core.conversation import save_message, load_conversation_window


def _make_user(db, telegram_id):
    user = User(telegram_id=telegram_id)
    db.session.add(user)
    db.session.commit()
    return user


def test_save_and_load(db, app):
    user = _make_user(db, 10001)
    save_message(user.id, 'training', 'user', 'Hello coach')
    save_message(user.id, 'training', 'assistant', 'Hello! Ready to train?')
    window = load_conversation_window(user.id, 'training')
    assert len(window) == 2
    assert window[0] == {'role': 'user', 'content': 'Hello coach'}
    assert window[1] == {'role': 'assistant', 'content': 'Hello! Ready to train?'}


def test_module_isolation(db, app):
    user = _make_user(db, 10002)
    save_message(user.id, 'training', 'user', 'Training msg')
    save_message(user.id, 'nutrition', 'user', 'Nutrition msg')
    training = load_conversation_window(user.id, 'training')
    nutrition = load_conversation_window(user.id, 'nutrition')
    assert len(training) == 1
    assert training[0]['content'] == 'Training msg'
    assert len(nutrition) == 1
    assert nutrition[0]['content'] == 'Nutrition msg'


def test_window_limit(db, app):
    user = _make_user(db, 10003)
    for i in range(20):
        save_message(user.id, 'training', 'user', f'msg {i}')
    window = load_conversation_window(user.id, 'training', limit=15)
    assert len(window) == 15
    # most recent 15 messages
    assert window[-1]['content'] == 'msg 19'
