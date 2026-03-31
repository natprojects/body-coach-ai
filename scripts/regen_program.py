"""One-time script: regenerate training program and insights for all active users."""
import sys
sys.path.insert(0, '/app')

from app import create_app
from app.modules.training.models import Program
from app.modules.training.coach import generate_program, save_program_from_dict, generate_exercise_insights
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
        print(f'Regenerating program for user {user.id} (lang={lang})')
        try:
            program_dict = generate_program(user)
            new_program = save_program_from_dict(user.id, program_dict)
            print(f'Program regenerated: {new_program.name}')
            count = generate_exercise_insights(new_program, user)
            print(f'Insights generated: {count} exercises')
        except Exception as e:
            print(f'ERROR for user {user.id}: {e}', file=sys.stderr)
