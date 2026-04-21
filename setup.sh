#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Church Meals Credit System — First-time setup
# ─────────────────────────────────────────────────────────────
set -e

echo "⛪ Church Meals Credit System — Setup"
echo "────────────────────────────────────"

# Install dependencies
echo "→ Installing Python dependencies…"
pip install -r requirements.txt

# Run migrations
echo "→ Applying database migrations…"
python manage.py migrate

# Seed sample data
echo "→ Seeding sample data…"
python manage.py seed_data

# Collect static files (for production)
# python manage.py collectstatic --noinput

echo ""
echo "✓ Setup complete!"
echo ""
echo "  Start the dev server:   python manage.py runserver"
echo "  Admin panel:            http://127.0.0.1:8000/admin/  (admin / admin123)"
echo "  Family login:           http://127.0.0.1:8000/"
echo "  Kiosk PIN:              1234"
echo ""
echo "  To top up a family:     python manage.py add_credits <family_id> <amount>"
