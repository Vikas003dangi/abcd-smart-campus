# 🏛️ ABCD Coaching & Smart Library Management Platform
### *Django 5.2 • Django Channels 4.3 WebSockets • Daphne ASGI • WhiteNoise • PostgreSQL/SQLite*

See the complete, illustrated documentation, architecture diagrams, and feature showcases in the [Root README](../README.md).

### Quick Commands (inside `abcd_web`):
```bash
# 1. Activate virtual environment
venv\Scripts\activate

# 2. Run system check & collect static files
python manage.py check
python manage.py collectstatic --noinput

# 3. Run development web server
python manage.py runserver

# 4. Run background automation daemon
python manage.py run_local_scheduler
```

For environment configuration, see `.env.example`.
