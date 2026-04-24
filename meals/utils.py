import hashlib
import os
from functools import wraps
from django.shortcuts import redirect


# ─── PIN hashing ──────────────────────────────────────────────────────────────

def hash_pin(pin: str) -> str:
    salt = os.urandom(16).hex()
    hashed = hashlib.sha256(f"{salt}{pin}".encode()).hexdigest()
    return f"{salt}:{hashed}"


def check_pin(pin: str, pin_hash: str) -> bool:
    try:
        salt, hashed = pin_hash.split(':', 1)
        expected = hashlib.sha256(f"{salt}{pin}".encode()).hexdigest()
        return expected == hashed
    except (ValueError, AttributeError):
        return False


# ─── Session decorators ───────────────────────────────────────────────────────

def require_family_session(view_func):
    """Family must be logged in AND session branch must match URL branch."""
    @wraps(view_func)
    def wrapper(request, branch_slug, *args, **kwargs):
        family_id   = request.session.get('family_id')
        session_slug = request.session.get('branch_slug')
        if not family_id or session_slug != branch_slug:
            return redirect('branch_family_login', branch_slug=branch_slug)
        return view_func(request, branch_slug, *args, **kwargs)
    return wrapper


def require_kiosk_session(view_func):
    """Kiosk must be authenticated AND session branch must match URL branch."""
    @wraps(view_func)
    def wrapper(request, branch_slug, *args, **kwargs):
        if not request.session.get('kiosk_authenticated'):
            return redirect('branch_kiosk_login', branch_slug=branch_slug)
        if request.session.get('kiosk_branch_slug') != branch_slug:
            return redirect('branch_kiosk_login', branch_slug=branch_slug)
        return view_func(request, branch_slug, *args, **kwargs)
    return wrapper


# ─── Theme CSS variables ──────────────────────────────────────────────────────

THEME_PALETTES = {
    'green': {
        'deep':   '#1a3a2a',
        'mid':    '#2d6a4f',
        'light':  '#52b788',
        'pale':   '#d8f3dc',
        'cream':  '#faf7f2',
    },
    'amber': {
        'deep':   '#3d2000',
        'mid':    '#a05c00',
        'light':  '#e09a3a',
        'pale':   '#fef3dc',
        'cream':  '#fdf8f0',
    },
    'coral': {
        'deep':   '#7a1a00',
        'mid':    '#d94f1e',
        'light':  '#ff8c69',
        'pale':   '#ffe5dc',
        'cream':  '#fff8f6',
    },
    'blue': {
        'deep':   '#003a5c',
        'mid':    '#1a6fa0',
        'light':  '#52aee0',
        'pale':   '#d8eef8',
        'cream':  '#f4faff',
    },
    'purple': {
        'deep':   '#2a1a4a',
        'mid':    '#5a2d8a',
        'light':  '#9b6dd0',
        'pale':   '#ede0f8',
        'cream':  '#f9f6ff',
    },
    'slate': {
        'deep':   '#1c2733',
        'mid':    '#3d5166',
        'light':  '#7a9bbf',
        'pale':   '#dde8f0',
        'cream':  '#f4f7fa',
    },
}

def get_theme_css(theme: str) -> str:
    """Return :root CSS variable overrides for a given theme slug."""
    p = THEME_PALETTES.get(theme, THEME_PALETTES['green'])
    return (
        f"--green-deep:{p['deep']};"
        f"--green-mid:{p['mid']};"
        f"--green-light:{p['light']};"
        f"--green-pale:{p['pale']};"
        f"--cream:{p['cream']};"
    )
