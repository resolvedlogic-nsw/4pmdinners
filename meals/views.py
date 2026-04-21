import json
import qrcode
import qrcode.image.svg
import io
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.utils import timezone
from django.db import transaction

from .models import Family, MealPricing, Transaction, QRCodeNonce
from .utils import hash_pin, check_pin, require_family_session, require_kiosk_session

KIOSK_PIN = '1234'  # In production, store in env/settings


# ─── Public ────────────────────────────────────────────────────────────────────

def index(request):
    if request.session.get('family_id'):
        return redirect('meals:user_summary')
    if request.session.get('kiosk_authenticated'):
        return redirect('meals:kiosk_home')
    return render(request, 'meals/index.html')


def families_json(request):
    """Lightweight endpoint for client-side family search."""
    families = Family.objects.filter(is_active=True).values('id', 'display_name', 'surname')
    return JsonResponse({'families': list(families)})


# ─── Family Auth ───────────────────────────────────────────────────────────────

def family_login(request):
    if request.method == 'POST':
        family_id = request.POST.get('family_id')
        pin = request.POST.get('pin', '')
        try:
            family = Family.objects.get(id=family_id, is_active=True)
        except Family.DoesNotExist:
            return render(request, 'meals/family_login.html', {'error': 'Family not found.'})

        if check_pin(pin, family.pin_hash):
            request.session['family_id'] = family.id
            request.session.set_expiry(60 * 60 * 24 * 180)
            return redirect('meals:user_summary')
        else:
            return render(request, 'meals/family_login.html', {
                'error': 'Incorrect PIN. Please try again.',
                'selected_family_id': family_id,
                'selected_family_name': family.display_name,
            })

    return render(request, 'meals/family_login.html')


def family_logout(request):
    request.session.flush()
    return redirect('meals:index')


# ─── Family Views ──────────────────────────────────────────────────────────────

@require_family_session
def user_summary(request):
    family = get_object_or_404(Family, id=request.session['family_id'])
    pricing = MealPricing.get_active_pricing()
    context = {
        'family': family,
        'adult_unit_cost': pricing['adult'],
        'child_unit_cost': pricing['child'],
        'max_adults': family.max_meals_of_type('adult'),
        'max_children': family.max_meals_of_type('child'),
    }
    return render(request, 'meals/user_summary.html', context)


@require_family_session
@require_POST
def generate_qr(request):
    family = get_object_or_404(Family, id=request.session['family_id'])
    pricing = MealPricing.get_active_pricing()

    try:
        adult_count = int(request.POST.get('adult_count', 0))
        child_count = int(request.POST.get('child_count', 0))
    except (ValueError, TypeError):
        messages.error(request, 'Invalid meal selection.')
        return redirect('meals:user_summary')

    if adult_count < 0 or child_count < 0 or (adult_count + child_count) == 0:
        messages.error(request, 'Please select at least one meal.')
        return redirect('meals:user_summary')

    total_cost = adult_count * pricing['adult'] + child_count * pricing['child']

    with transaction.atomic():
        family = Family.objects.select_for_update().get(id=family.id)
        if family.credit_units < total_cost:
            messages.error(request, 'Insufficient credits.')
            return redirect('meals:user_summary')

        nonce = QRCodeNonce.objects.create(
            family=family,
            credit_units=total_cost,
            adult_count=adult_count,
            child_count=child_count,
            created_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=30),
        )

    return redirect('meals:qr_display', nonce_id=nonce.id)


@require_family_session
def qr_display(request, nonce_id):
    family = get_object_or_404(Family, id=request.session['family_id'])
    nonce = get_object_or_404(QRCodeNonce, id=nonce_id, family=family)

    if nonce.used:
        return render(request, 'meals/qr_success.html', {'nonce': nonce, 'family': family})

    if timezone.now() > nonce.expires_at:
        return render(request, 'meals/qr_expired.html', {'family': family})

    payload = f"v1|{family.id}|{nonce.id}"
    svg_data = _generate_qr_svg(payload)

    context = {
        'family': family,
        'nonce': nonce,
        'qr_svg': svg_data,
        'expires_at_iso': nonce.expires_at.isoformat(),
    }
    return render(request, 'meals/qr_display.html', context)


@require_GET
def qr_status(request, nonce_id):
    """Polling endpoint: returns whether nonce has been used."""
    try:
        nonce = QRCodeNonce.objects.get(id=nonce_id)
    except QRCodeNonce.DoesNotExist:
        return JsonResponse({'status': 'not_found'}, status=404)

    if nonce.used:
        return JsonResponse({'status': 'used', 'balance': nonce.family.credit_units})
    if timezone.now() > nonce.expires_at:
        return JsonResponse({'status': 'expired'})
    return JsonResponse({'status': 'pending'})


@require_family_session
def change_pin(request):
    family = get_object_or_404(Family, id=request.session['family_id'])
    if request.method == 'POST':
        current_pin = request.POST.get('current_pin', '')
        new_pin = request.POST.get('new_pin', '')
        confirm_pin = request.POST.get('confirm_pin', '')

        if not check_pin(current_pin, family.pin_hash):
            return render(request, 'meals/change_pin.html', {
                'family': family, 'error': 'Current PIN is incorrect.'
            })
        if len(new_pin) < 4 or len(new_pin) > 6 or not new_pin.isdigit():
            return render(request, 'meals/change_pin.html', {
                'family': family, 'error': 'PIN must be 4–6 digits.'
            })
        if new_pin != confirm_pin:
            return render(request, 'meals/change_pin.html', {
                'family': family, 'error': 'PINs do not match.'
            })

        family.pin_hash = hash_pin(new_pin)
        family.save(update_fields=['pin_hash'])
        messages.success(request, 'PIN updated successfully.')
        return redirect('meals:user_summary')

    return render(request, 'meals/change_pin.html', {'family': family})


# ─── Kiosk Auth ────────────────────────────────────────────────────────────────

def kiosk_login(request):
    if request.method == 'POST':
        pin = request.POST.get('pin', '')
        if pin == KIOSK_PIN:
            request.session['kiosk_authenticated'] = True
            request.session.set_expiry(60 * 60 * 12)
            return redirect('meals:kiosk_home')
        return render(request, 'meals/kiosk_login.html', {'error': 'Incorrect kiosk PIN.'})
    return render(request, 'meals/kiosk_login.html')


def kiosk_logout(request):
    request.session.pop('kiosk_authenticated', None)
    return redirect('meals:index')


# ─── Kiosk Views ───────────────────────────────────────────────────────────────

@require_kiosk_session
def kiosk_scanner(request):
    return render(request, 'meals/kiosk_scanner.html')


@require_kiosk_session
def kiosk_manual(request):
    families = Family.objects.filter(is_active=True).order_by('surname', 'display_name')
    return render(request, 'meals/kiosk_manual.html', {'families': families})


@require_kiosk_session
def kiosk_family_detail(request, family_id):
    family = get_object_or_404(Family, id=family_id, is_active=True)
    pricing = MealPricing.get_active_pricing()
    recent_transactions = family.transactions.all()[:10]
    context = {
        'family': family,
        'adult_unit_cost': pricing['adult'],
        'child_unit_cost': pricing['child'],
        'max_adults': family.max_meals_of_type('adult'),
        'max_children': family.max_meals_of_type('child'),
        'recent_transactions': recent_transactions,
    }
    return render(request, 'meals/kiosk_family_detail.html', context)


# ─── API Endpoints ─────────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
@require_kiosk_session
def api_redeem_qr(request):
    try:
        data = json.loads(request.body)
        payload = data.get('payload', '')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)

    parts = payload.split('|')
    if len(parts) != 3 or parts[0] != 'v1':
        return JsonResponse({'success': False, 'error': 'Invalid QR code format.'}, status=400)

    try:
        family_id = int(parts[1])
        nonce_id = parts[2]
    except (ValueError, IndexError):
        return JsonResponse({'success': False, 'error': 'Malformed QR code.'}, status=400)

    with transaction.atomic():
        try:
            nonce = QRCodeNonce.objects.select_for_update().get(id=nonce_id, family_id=family_id)
        except QRCodeNonce.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'QR code not found.'}, status=404)

        if not nonce.is_valid():
            msg = 'QR code already used.' if nonce.used else 'QR code has expired.'
            return JsonResponse({'success': False, 'error': msg}, status=400)

        family = Family.objects.select_for_update().get(id=family_id)
        if family.credit_units < nonce.credit_units:
            return JsonResponse({'success': False, 'error': 'Insufficient credits.'}, status=400)

        family.credit_units -= nonce.credit_units
        family.save(update_fields=['credit_units'])

        nonce.used = True
        nonce.save(update_fields=['used'])

        Transaction.objects.create(
            family=family,
            credit_delta=-nonce.credit_units,
            reason='qr_redemption',
            performed_by='system_qr',
            notes=f"{nonce.adult_count} adult(s), {nonce.child_count} child(ren)",
        )

    return JsonResponse({
        'success': True,
        'family_name': family.display_name,
        'credits_deducted': nonce.credit_units,
        'new_balance': family.credit_units,
        'adult_count': nonce.adult_count,
        'child_count': nonce.child_count,
    })


@csrf_exempt
@require_POST
@require_kiosk_session
def api_kiosk_deduct(request):
    try:
        data = json.loads(request.body)
        family_id = int(data.get('family_id'))
        adult_count = int(data.get('adult_count', 0))
        child_count = int(data.get('child_count', 0))
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Invalid request data.'}, status=400)

    if adult_count < 0 or child_count < 0 or (adult_count + child_count) == 0:
        return JsonResponse({'success': False, 'error': 'Select at least one meal.'}, status=400)

    pricing = MealPricing.get_active_pricing()
    total_cost = adult_count * pricing['adult'] + child_count * pricing['child']

    with transaction.atomic():
        try:
            family = Family.objects.select_for_update().get(id=family_id, is_active=True)
        except Family.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Family not found.'}, status=404)

        if family.credit_units < total_cost:
            return JsonResponse({'success': False, 'error': 'Insufficient credits.'}, status=400)

        family.credit_units -= total_cost
        family.save(update_fields=['credit_units'])

        Transaction.objects.create(
            family=family,
            credit_delta=-total_cost,
            reason='manual_kiosk_entry',
            performed_by='kiosk_volunteer',
            notes=f"{adult_count} adult(s), {child_count} child(ren)",
        )

    return JsonResponse({
        'success': True,
        'family_name': family.display_name,
        'credits_deducted': total_cost,
        'new_balance': family.credit_units,
    })

@require_POST
def api_kiosk_topup(request):
    try:
        data = json.loads(request.body)
        family_id = data.get('family_id')
        amount = int(data.get('amount', 0))

        if amount <= 0:
            return JsonResponse({'success': False, 'error': 'Invalid amount.'})

        with transaction.atomic():
            # select_for_update() locks the row until the transaction completes
            family = Family.objects.select_for_update().get(id=family_id)
            
            # 1. Update the balance
            family.credit_units += amount
            family.save()

            # 2. Log the audit trail
            Transaction.objects.create(
                family=family,
                credit_delta=amount,  # Positive number for top-ups
                reason='credit_top_up',
                performed_by='kiosk_volunteer',
                timestamp=timezone.now()
            )

            return JsonResponse({
                'success': True,
                'family_name': family.display_name,
                'new_balance': family.credit_units
            })

    except Family.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Family not found.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
# ─── Helpers ───────────────────────────────────────────────────────────────────

def _generate_qr_svg(payload: str) -> str:
    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(payload, image_factory=factory, box_size=10, border=2)
    stream = io.BytesIO()
    img.save(stream)
    return stream.getvalue().decode('utf-8')

@require_kiosk_session
@require_POST
def api_kiosk_add_family(request):
    try:
        data = json.loads(request.body)
        surname = data.get('surname', '').strip()
        contact = data.get('primary_contact', '').strip()
        pin = data.get('pin', '').strip()

        if not surname or not contact or not pin:
            return JsonResponse({'success': False, 'error': 'All fields are required.'})
        
        if len(pin) < 4:
            return JsonResponse({'success': False, 'error': 'PIN must be at least 4 digits.'})

        # Format public display name (e.g., "O'Shea — Connan")
        display_name = f"{surname} — {contact}"

        with transaction.atomic():
            family = Family.objects.create(
                surname=surname,
                primary_contact=contact,
                display_name=display_name,
                pin_hash=hash_pin(pin),
                credit_units=0,
                is_active=True
            )

            return JsonResponse({
                'success': True,
                'family_id': family.id,
                'display_name': family.display_name
            })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@require_kiosk_session
def kiosk_home(request):
    return render(request, 'meals/kiosk_home.html')