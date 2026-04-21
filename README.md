# ⛪ Church Meals Credit System

A lightweight Django web application for managing prepaid meal credits at church events. Families purchase credits in advance and redeem them via QR code or manual kiosk entry.

## Quick Start

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Run setup (installs deps, migrates DB, seeds sample data)
bash setup.sh

# 3. Start the dev server
python manage.py runserver
```

Then open http://127.0.0.1:8000/

## Credentials (dev/seed)

| Role         | Login                                    |
|--------------|------------------------------------------|
| Admin panel  | http://127.0.0.1:8000/admin/ — `admin` / `admin123` |
| Kiosk PIN    | `1234`                                   |
| Family PIN   | Each family's DDMM birthday (see seed_data.py) |

## Project Structure

```
church_meals/
├── config/              # Django project settings & root URLs
│   ├── settings.py
│   └── urls.py
├── meals/               # Main application
│   ├── models.py        # Family, MealPricing, Transaction, QRCodeNonce
│   ├── views.py         # All views + API endpoints
│   ├── urls.py          # URL routing
│   ├── utils.py         # PIN hashing, session decorators
│   ├── admin.py         # Django admin config
│   └── management/
│       └── commands/
│           ├── seed_data.py   # Populate sample families & pricing
│           └── add_credits.py # Top up a family's balance
├── templates/
│   ├── base.html              # Shared layout + full CSS design system
│   └── meals/
│       ├── index.html              # Landing page
│       ├── family_login.html       # Surname search + PIN login
│       ├── user_summary.html       # Credit balance + meal selector
│       ├── qr_display.html         # QR code + 30-min countdown
│       ├── qr_success.html         # Post-scan confirmation
│       ├── qr_expired.html         # Expired code screen
│       ├── change_pin.html         # PIN change form
│       ├── kiosk_login.html        # Kiosk PIN entry
│       ├── kiosk_scanner.html      # Camera QR scanner
│       ├── kiosk_manual.html       # Manual family search
│       └── kiosk_family_detail.html # Manual credit deduction
├── requirements.txt
├── setup.sh
└── manage.py
```

## URL Map

| URL                              | View                  | Who        |
|----------------------------------|-----------------------|------------|
| `/`                              | index                 | Public     |
| `/login/`                        | family_login          | Families   |
| `/logout/`                       | family_logout         | Families   |
| `/summary/`                      | user_summary          | Families   |
| `/qr/generate/`                  | generate_qr (POST)    | Families   |
| `/qr/display/<uuid>/`            | qr_display            | Families   |
| `/qr/status/<uuid>/`             | qr_status (poll)      | Families   |
| `/pin/change/`                   | change_pin            | Families   |
| `/kiosk/`                        | kiosk_login           | Kiosk      |
| `/kiosk/scanner/`                | kiosk_scanner         | Kiosk      |
| `/kiosk/manual/`                 | kiosk_manual          | Kiosk      |
| `/kiosk/family/<id>/`            | kiosk_family_detail   | Kiosk      |
| `/api/qr/redeem/`                | api_redeem_qr (POST)  | Kiosk API  |
| `/api/kiosk/deduct/`             | api_kiosk_deduct (POST)| Kiosk API |
| `/families/json/`                | families_json         | Public API |

## Key Design Decisions

- **Credits are abstract integers**, never shown as dollars to families or volunteers.
- **QR nonces** are single-use UUIDs with a 30-minute expiry enforced atomically at redemption time.
- **Sessions** are 6-month persistent cookies for families (avoiding weekly re-login in poor reception), 12-hour for kiosks.
- **PIN hashing** uses SHA-256 with a random salt (not bcrypt to minimise dependencies, but easily swappable).
- **All deductions use `select_for_update()`** inside a `db_transaction.atomic()` block to prevent double-spending.
- **No CDN dependencies** for core functionality — jsQR is the only external script and only needed on the kiosk scanner page.

## Production Checklist

- [ ] Set `SECRET_KEY` via environment variable
- [ ] Set `DEBUG=False`
- [ ] Switch `DATABASES` to PostgreSQL
- [ ] Set `KIOSK_PIN` via environment variable (or DB-backed setting)
- [ ] Run `python manage.py collectstatic`
- [ ] Serve behind nginx/gunicorn with HTTPS
- [ ] Set `SESSION_COOKIE_SECURE = True`
- [ ] Replace SHA-256 PIN hashing with `django.contrib.auth.hashers.make_password`
