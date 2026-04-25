try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv only needed for local dev; prod sets env vars directly

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
