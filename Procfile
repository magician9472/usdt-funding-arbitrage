release: alembic -c backend/alembic.ini upgrade head
web: uvicorn backend.main:app --host 0.0.0.0 --port 8080