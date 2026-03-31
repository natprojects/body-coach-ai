FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip install gunicorn

COPY . .

RUN mkdir -p /app/data

ENV DATABASE_URL=sqlite:////app/data/body_coach.db

EXPOSE 8000

CMD ["gunicorn", "run:app", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "180"]
