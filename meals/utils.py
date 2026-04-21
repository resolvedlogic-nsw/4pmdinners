import hashlib
import os
from functools import wraps
from django.shortcuts import redirect


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


def require_family_session(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get('family_id'):
            return redirect('meals:family_login')
        return view_func(request, *args, **kwargs)
    return wrapper


def require_kiosk_session(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get('kiosk_authenticated'):
            return redirect('meals:kiosk_login')
        return view_func(request, *args, **kwargs)
    return wrapper
