"""One-time script: regenerate exercise insights for all active programs."""
import sys
sys.path.insert(0, '/app')

from app import create_app
from app.modules.training.models import Program
from app.modules.training.coach import generate_exercise_insights
from app.core.models import User

app = create_app()
with app.app_context():
    programs = Program.query.filter_by(status='active').all()
    if not programs:
        print('No active programs found.')
        sys.exit(0)
    for p in programs:
        user = User.query.get(p.user_id)
        lang = getattr(user, 'app_language', 'en') or 'en'
        print(f'Regenerating insights for program {p.id}, user lang={lang}')
        count = generate_exercise_insights(p, user)
        print(f'Done: {count} exercises updated')
