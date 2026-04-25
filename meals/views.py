import json
import csv
import qrcode
import qrcode.image.svg
import io
from decimal import Decimal
from datetime import date

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from django.conf import settings

from .models import (Branch, Product, Family, Child, Transaction, QRCodeNonce,
                     AttendanceRecord, AttendanceChild, SquarePaymentOrder)
from .utils import hash_pin, check_pin, require_family_session, require_kiosk_session, get_theme_css


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_branch_or_404(slug):
    return get_object_or_404(Branch, slug=slug, is_active=True)


def branch_ctx(branch):
    return {'branch': branch, 'theme_css': get_theme_css(branch.theme)}


def make_qr_svg(data: str) -> str:
    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(data, image_factory=factory, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode('utf-8')


def _site_base_url(request):
    """Returns e.g. https://4pmdinners.pythonanywhere.com"""
    return f"{request.scheme}://{request.get_host()}"


# ─── Home ─────────────────────────────────────────────────────────────────────

def home(request):
    branches = Branch.objects.filter(is_active=True)
    return render(request, 'home.html', {'branches': branches})


# ─── Branch index ─────────────────────────────────────────────────────────────

def branch_index(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    return render(request, 'meals/branch_index.html', branch_ctx(branch))


# ─── Family auth ──────────────────────────────────────────────────────────────

def family_login(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    ctx = branch_ctx(branch)
    ctx['error'] = None

    if request.method == 'POST':
        family_id = request.POST.get('family_id')
        pin = request.POST.get('pin', '')
        try:
            family = Family.objects.get(id=family_id, branch=branch, is_active=True)
            if check_pin(pin, family.pin_hash):
                request.session['family_id'] = family.id
                request.session['branch_slug'] = branch_slug
                return redirect('branch_user_summary', branch_slug=branch_slug)
            ctx['error'] = 'Incorrect PIN.'
        except Family.DoesNotExist:
            ctx['error'] = 'Family not found.'
        ctx['selected_family_id'] = family_id
        ctx['selected_family_name'] = request.POST.get('family_name', '')

    return render(request, 'meals/family_login.html', ctx)


def family_logout(request, branch_slug):
    request.session.flush()
    return redirect('branch_index', branch_slug=branch_slug)


def families_json(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    families = Family.objects.filter(branch=branch, is_active=True).values('id', 'surname', 'display_name')
    return JsonResponse({'families': list(families)})


# ─── Family summary & QR flow ─────────────────────────────────────────────────

@require_family_session
def user_summary(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    family = get_object_or_404(Family, id=request.session['family_id'], branch=branch)
    products = branch.products.filter(is_active=True)
    ctx = branch_ctx(branch)
    ctx['family'] = family
    ctx['products'] = products
    ctx['has_online_topup'] = products.filter(price_aud__isnull=False).exclude(price_aud=0).exists()
    if branch.is_children_programme:
        ctx['children'] = family.children.filter(is_active=True)
    return render(request, 'meals/user_summary.html', ctx)


@require_family_session
@require_POST
def generate_qr(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    family = get_object_or_404(Family, id=request.session['family_id'], branch=branch)
    products = branch.products.filter(is_active=True)

    if branch.is_children_programme:
        child_ids = [int(x) for x in request.POST.getlist('child_ids') if x.isdigit()]
        children = Child.objects.filter(id__in=child_ids, family=family, is_active=True)
        actual_ids = list(children.values_list('id', flat=True))
        count = len(actual_ids)
        if count == 0:
            messages.error(request, 'Please select at least one child.')
            return redirect('branch_user_summary', branch_slug=branch_slug)
        total_cost = Decimal(count)
        if not family.can_afford(total_cost):
            messages.error(request, 'Insufficient credits.')
            return redirect('branch_user_summary', branch_slug=branch_slug)
        nonce = QRCodeNonce.objects.create(family=family, credit_units=total_cost, child_ids=actual_ids)
    else:
        total_cost = Decimal(0)
        product_quantities = {}
        for product in products:
            try:
                qty = max(0, int(request.POST.get(f'qty_{product.id}', '0')))
            except ValueError:
                qty = 0
            if qty > 0:
                product_quantities[product.id] = qty
                total_cost += product.credit_cost * qty
        if total_cost == 0:
            messages.error(request, 'Please select at least one item.')
            return redirect('branch_user_summary', branch_slug=branch_slug)
        if not family.can_afford(total_cost):
            messages.error(request, 'Insufficient credits.')
            return redirect('branch_user_summary', branch_slug=branch_slug)
        product_list = [{'id': pid, 'qty': qty} for pid, qty in product_quantities.items()]
        nonce = QRCodeNonce.objects.create(family=family, credit_units=total_cost, child_ids=product_list)

    return redirect('branch_qr_display', branch_slug=branch_slug, nonce_id=nonce.id)


@require_family_session
def qr_display(request, branch_slug, nonce_id):
    branch = get_branch_or_404(branch_slug)
    family = get_object_or_404(Family, id=request.session['family_id'], branch=branch)
    nonce = get_object_or_404(QRCodeNonce, id=nonce_id, family=family)
    if not nonce.is_valid():
        return render(request, 'meals/qr_expired.html', branch_ctx(branch))
    qr_svg = make_qr_svg(str(nonce.id))
    ctx = branch_ctx(branch)
    ctx.update({'nonce': nonce, 'family': family, 'qr_svg': qr_svg, 'expires_at_iso': nonce.expires_at.isoformat()})
    if branch.is_children_programme:
        ctx['selected_children'] = Child.objects.filter(id__in=nonce.child_ids)
    return render(request, 'meals/qr_display.html', ctx)


def qr_status(request, branch_slug, nonce_id):
    nonce = get_object_or_404(QRCodeNonce, id=nonce_id)
    if nonce.used:
        return JsonResponse({'status': 'used'})
    if not nonce.is_valid():
        return JsonResponse({'status': 'expired'})
    return JsonResponse({'status': 'pending'})


@require_family_session
def change_pin(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    family = get_object_or_404(Family, id=request.session['family_id'], branch=branch)
    ctx = branch_ctx(branch)
    ctx['family'] = family
    if request.method == 'POST':
        current = request.POST.get('current_pin', '')
        new_pin = request.POST.get('new_pin', '')
        confirm = request.POST.get('confirm_pin', '')
        if not check_pin(current, family.pin_hash):
            ctx['error'] = 'Current PIN is incorrect.'
        elif len(new_pin) < 4:
            ctx['error'] = 'New PIN must be at least 4 digits.'
        elif new_pin != confirm:
            ctx['error'] = 'New PINs do not match.'
        else:
            family.pin_hash = hash_pin(new_pin)
            family.save(update_fields=['pin_hash'])
            messages.success(request, 'PIN updated successfully.')
            return redirect('branch_user_summary', branch_slug=branch_slug)
    return render(request, 'meals/change_pin.html', ctx)


# ─── Online Top-Up (Square) ───────────────────────────────────────────────────

@require_family_session
def topup_select(request, branch_slug):
    """Shows available online top-up bundles for this branch."""
    branch = get_branch_or_404(branch_slug)
    family = get_object_or_404(Family, id=request.session['family_id'], branch=branch)
    online_products = branch.products.filter(is_active=True, price_aud__isnull=False).exclude(price_aud=0)

    if not online_products.exists():
        messages.info(request, 'Online top-up is not available for this programme.')
        return redirect('branch_user_summary', branch_slug=branch_slug)

    ctx = branch_ctx(branch)
    ctx.update({'family': family, 'online_products': online_products})
    return render(request, 'meals/topup_select.html', ctx)


@require_family_session
@require_POST
def topup_checkout(request, branch_slug):
    """Creates a Square payment link and redirects the family to Square to pay."""
    from .square_service import create_payment_link

    branch = get_branch_or_404(branch_slug)
    family = get_object_or_404(Family, id=request.session['family_id'], branch=branch)

    product_id = request.POST.get('product_id')
    try:
        quantity = max(1, int(request.POST.get('quantity', 1)))
    except ValueError:
        quantity = 1

    product = get_object_or_404(Product, id=product_id, branch=branch, is_active=True)

    if not product.available_online:
        messages.error(request, 'That product is not available for online purchase.')
        return redirect('branch_topup_select', branch_slug=branch_slug)

    total_aud = product.price_aud * quantity
    credits_to_add = Decimal(product.topup_credits) * quantity

    # Create our internal order record first
    order = SquarePaymentOrder.objects.create(
        family=family,
        product=product,
        quantity=quantity,
        credits_to_add=credits_to_add,
        amount_aud=total_aud,
    )

    base = _site_base_url(request)
    success_url = f"{base}/{branch_slug}/topup/success/?order={order.id}"
    cancel_url  = f"{base}/{branch_slug}/topup/cancel/"

    try:
        link_url, square_order_id, link_id = create_payment_link(order, success_url, cancel_url)
        order.square_order_id = square_order_id
        order.square_payment_link_id = link_id
        order.save(update_fields=['square_order_id', 'square_payment_link_id'])
        return redirect(link_url)
    except Exception as e:
        order.status = 'failed'
        order.save(update_fields=['status'])
        messages.error(request, f'Could not create payment link: {e}')
        return redirect('branch_topup_select', branch_slug=branch_slug)


@require_family_session
def topup_success(request, branch_slug):
    """
    Square redirects here after a successful payment.
    We verify with Square then credit the family's account.
    """
    from .square_service import verify_payment

    branch = get_branch_or_404(branch_slug)
    family = get_object_or_404(Family, id=request.session['family_id'], branch=branch)

    order_id = request.GET.get('order')
    try:
        order = SquarePaymentOrder.objects.get(id=order_id, family=family)
    except SquarePaymentOrder.DoesNotExist:
        messages.error(request, 'Order not found.')
        return redirect('branch_user_summary', branch_slug=branch_slug)

    # Guard against double-processing
    if order.status == 'completed':
        ctx = branch_ctx(branch)
        ctx.update({'family': family, 'order': order, 'already_processed': True})
        return render(request, 'meals/topup_success.html', ctx)

    # Verify with Square that money actually arrived
    paid = verify_payment(order.square_order_id) if order.square_order_id else False

    if paid:
        family.credit_units += order.credits_to_add
        family.save(update_fields=['credit_units'])

        Transaction.objects.create(
            family=family,
            credit_delta=order.credits_to_add,
            reason='online_topup',
            performed_by='square_online',
            notes=(
                f"Square online: {order.quantity}× {order.product.name} "
                f"(${order.amount_aud} AUD) → +{order.credits_to_add} credits"
            ),
        )

        order.status = 'completed'
        order.completed_at = timezone.now()
        order.save(update_fields=['status', 'completed_at'])

        ctx = branch_ctx(branch)
        ctx.update({'family': family, 'order': order, 'already_processed': False})
        return render(request, 'meals/topup_success.html', ctx)

    else:
        # Payment not confirmed — could be a timing issue; show pending message
        # Credits are NOT added until Square confirms
        ctx = branch_ctx(branch)
        ctx.update({'family': family, 'order': order, 'payment_pending': True})
        return render(request, 'meals/topup_success.html', ctx)


@require_family_session
def topup_cancel(request, branch_slug):
    """Family cancelled out of Square — just send them back."""
    branch = get_branch_or_404(branch_slug)
    messages.info(request, 'Payment cancelled — no charge was made.')
    return redirect('branch_user_summary', branch_slug=branch_slug)


@csrf_exempt
@require_POST
def topup_webhook(request, branch_slug):
    """
    Square webhook endpoint — receives payment.completed events.
    Provides a safety net in case the redirect-based verification above
    is missed (e.g. browser closed before redirect).
    """
    from .square_service import verify_payment

    try:
        payload = json.loads(request.body)
        event_type = payload.get('type', '')

        if event_type == 'payment.completed':
            payment = payload.get('data', {}).get('object', {}).get('payment', {})
            order_id_sq = payment.get('order_id', '')

            # Find our internal order by Square order ID
            try:
                order = SquarePaymentOrder.objects.get(
                    square_order_id=order_id_sq,
                    status='pending'
                )
            except SquarePaymentOrder.DoesNotExist:
                return HttpResponse(status=200)  # already processed or unknown

            order.square_payment_id = payment.get('id', '')
            order.save(update_fields=['square_payment_id'])

            family = order.family
            family.credit_units += order.credits_to_add
            family.save(update_fields=['credit_units'])

            Transaction.objects.create(
                family=family,
                credit_delta=order.credits_to_add,
                reason='online_topup',
                performed_by='square_online',
                notes=(
                    f"Square webhook: {order.quantity}× {order.product.name} "
                    f"(${order.amount_aud} AUD) → +{order.credits_to_add} credits"
                ),
            )

            order.status = 'completed'
            order.completed_at = timezone.now()
            order.save(update_fields=['status', 'completed_at'])

    except Exception:
        pass  # Never return an error to Square — it will retry repeatedly

    return HttpResponse(status=200)


# ─── Kiosk auth ───────────────────────────────────────────────────────────────

def kiosk_login(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    ctx = branch_ctx(branch)
    if request.method == 'POST':
        pin = request.POST.get('pin', '')
        if check_pin(pin, branch.kiosk_pin_hash):
            request.session['kiosk_authenticated'] = True
            request.session['kiosk_branch_slug'] = branch_slug
            return redirect('branch_kiosk_home', branch_slug=branch_slug)
        ctx['error'] = 'Incorrect kiosk PIN.'
    return render(request, 'meals/kiosk_login.html', ctx)


@require_kiosk_session
def kiosk_home(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    return render(request, 'meals/kiosk_home.html', branch_ctx(branch))


def kiosk_logout(request, branch_slug):
    request.session.pop('kiosk_authenticated', None)
    request.session.pop('kiosk_branch_slug', None)
    return redirect('branch_kiosk_login', branch_slug=branch_slug)


@require_kiosk_session
def kiosk_scanner(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    return render(request, 'meals/kiosk_scanner.html', branch_ctx(branch))


@require_kiosk_session
def kiosk_manual(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    families = Family.objects.filter(branch=branch, is_active=True)
    ctx = branch_ctx(branch)
    ctx['families'] = families
    return render(request, 'meals/kiosk_manual.html', ctx)


@require_kiosk_session
def kiosk_family_detail(request, branch_slug, family_id):
    branch = get_branch_or_404(branch_slug)
    family = get_object_or_404(Family, id=family_id, branch=branch)
    ctx = branch_ctx(branch)
    ctx.update({
        'family': family,
        'products': branch.products.filter(is_active=True),
        'recent_transactions': family.transactions.all()[:10],
    })
    if branch.is_children_programme:
        ctx['children'] = family.children.filter(is_active=True)
    return render(request, 'meals/kiosk_family_detail.html', ctx)


@require_kiosk_session
def kiosk_manage_children(request, branch_slug, family_id):
    branch = get_branch_or_404(branch_slug)
    family = get_object_or_404(Family, id=family_id, branch=branch)
    ctx = branch_ctx(branch)
    ctx.update({'family': family, 'children': family.children.all()})
    return render(request, 'meals/kiosk_manage_children.html', ctx)


@require_kiosk_session
def kiosk_export_attendance(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    session_date_str = request.GET.get('date', str(date.today()))
    try:
        session_date = date.fromisoformat(session_date_str)
    except ValueError:
        session_date = date.today()
    records = (AttendanceRecord.objects
               .filter(branch=branch, session_date=session_date)
               .prefetch_related('children_present__child', 'family'))
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{branch_slug}_attendance_{session_date}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Family', 'Primary Contact', 'Child', 'Check-in Time'])
    for record in records:
        for cp in record.children_present.all():
            writer.writerow([record.family.display_name, record.family.primary_contact,
                             cp.child.full_name, record.timestamp.strftime('%H:%M')])
    return response


@require_kiosk_session
def kiosk_export_roster(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    families = Family.objects.filter(branch=branch, is_active=True).prefetch_related('children')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{branch_slug}_roster.csv"'
    writer = csv.writer(response)
    writer.writerow(['Family', 'Primary Contact', 'Child First Name', 'Child Last Name', 'DOB', 'Active'])
    for family in families:
        for child in family.children.all():
            writer.writerow([family.display_name, family.primary_contact,
                             child.first_name, child.last_name,
                             child.date_of_birth or '', 'Yes' if child.is_active else 'No'])
    return response


# ─── API: QR redemption ───────────────────────────────────────────────────────

@require_POST
def api_redeem_qr(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    if not request.session.get('kiosk_authenticated') or request.session.get('kiosk_branch_slug') != branch_slug:
        return JsonResponse({'success': False, 'error': 'Not authorised.'}, status=403)
    try:
        payload = json.loads(request.body)
        nonce_id = payload.get('payload') or payload.get('nonce_id')
        nonce = QRCodeNonce.objects.select_related('family').get(id=nonce_id)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid QR code.'})
    if nonce.family.branch_id != branch.id:
        return JsonResponse({'success': False, 'error': 'QR code is for a different branch.'})
    if not nonce.is_valid():
        return JsonResponse({'success': False, 'error': 'QR code has expired or already been used.'})
    family = nonce.family
    family.credit_units -= nonce.credit_units
    family.save(update_fields=['credit_units'])
    txn = Transaction.objects.create(family=family, credit_delta=-nonce.credit_units,
                                     reason='qr_redemption', performed_by='system_qr')
    nonce.used = True
    nonce.save(update_fields=['used'])
    response_data = {'success': True, 'family_name': family.display_name,
                     'credits_deducted': float(nonce.credit_units), 'new_balance': float(family.credit_units)}
    if branch.is_children_programme and nonce.child_ids:
        child_ids = [x for x in nonce.child_ids if isinstance(x, int)]
        if child_ids:
            record = AttendanceRecord.objects.create(branch=branch, family=family,
                                                     session_date=timezone.localdate(), transaction=txn)
            children = Child.objects.filter(id__in=child_ids, family=family)
            for child in children:
                AttendanceChild.objects.create(record=record, child=child)
            response_data['children_checked_in'] = [c.full_name for c in children]
    return JsonResponse(response_data)


# ─── API: Manual deduction ────────────────────────────────────────────────────

@require_POST
def api_kiosk_deduct(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    if not request.session.get('kiosk_authenticated') or request.session.get('kiosk_branch_slug') != branch_slug:
        return JsonResponse({'success': False, 'error': 'Not authorised.'}, status=403)
    try:
        data = json.loads(request.body)
        family = Family.objects.get(id=data['family_id'], branch=branch)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid request.'})
    if branch.is_children_programme:
        child_ids = [int(x) for x in data.get('child_ids', []) if str(x).isdigit()]
        count = len(child_ids)
        if count == 0:
            return JsonResponse({'success': False, 'error': 'No children selected.'})
        total_cost = Decimal(count)
    else:
        products = branch.products.filter(is_active=True)
        total_cost = Decimal(0)
        for product in products:
            qty = int(data.get(f'qty_{product.id}', 0))
            total_cost += product.credit_cost * qty
    if total_cost <= 0:
        return JsonResponse({'success': False, 'error': 'Nothing to deduct.'})
    if family.credit_units < total_cost:
        return JsonResponse({'success': False, 'error': 'Insufficient credits.'})
    family.credit_units -= total_cost
    family.save(update_fields=['credit_units'])
    txn = Transaction.objects.create(family=family, credit_delta=-total_cost,
                                     reason='manual_kiosk', performed_by='kiosk_volunteer',
                                     notes=data.get('notes', ''))
    if branch.is_children_programme and child_ids:
        record = AttendanceRecord.objects.create(branch=branch, family=family,
                                                 session_date=timezone.localdate(), transaction=txn)
        children = Child.objects.filter(id__in=child_ids, family=family)
        for child in children:
            AttendanceChild.objects.create(record=record, child=child)
    return JsonResponse({'success': True, 'family_name': family.display_name,
                         'credits_deducted': float(total_cost), 'new_balance': float(family.credit_units)})


# ─── API: Kiosk top-up ────────────────────────────────────────────────────────

@require_POST
def api_kiosk_topup(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    if not request.session.get('kiosk_authenticated') or request.session.get('kiosk_branch_slug') != branch_slug:
        return JsonResponse({'success': False, 'error': 'Not authorised.'}, status=403)
    try:
        data = json.loads(request.body)
        family = Family.objects.get(id=data['family_id'], branch=branch)
        amount = Decimal(str(data['amount']))
        assert amount > 0
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid request.'})
    family.credit_units += amount
    family.save(update_fields=['credit_units'])
    Transaction.objects.create(family=family, credit_delta=amount, reason='credit_top_up',
                               performed_by='kiosk_volunteer', notes=data.get('notes', ''))
    return JsonResponse({'success': True, 'new_balance': float(family.credit_units)})


# ─── API: Add family ──────────────────────────────────────────────────────────

@require_POST
def api_kiosk_add_family(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    if not request.session.get('kiosk_authenticated') or request.session.get('kiosk_branch_slug') != branch_slug:
        return JsonResponse({'success': False, 'error': 'Not authorised.'}, status=403)
    try:
        data = json.loads(request.body)
        surname = data['surname'].strip()
        contact = data['primary_contact'].strip()
        pin = data['pin'].strip()
        display = data.get('display_name', '').strip() or f"{surname} — {contact}"
        assert surname and contact and len(pin) >= 4
    except Exception:
        return JsonResponse({'success': False, 'error': 'Please fill all fields (PIN must be ≥4 digits).'})
    if Family.objects.filter(branch=branch, surname=surname, primary_contact=contact).exists():
        return JsonResponse({'success': False, 'error': 'A family with that surname and contact already exists.'})
    family = Family.objects.create(branch=branch, surname=surname, primary_contact=contact,
                                   display_name=display, pin_hash=hash_pin(pin), credit_units=0)
    return JsonResponse({'success': True, 'family_id': family.id})


# ─── API: Child management ────────────────────────────────────────────────────

@require_POST
def api_kiosk_add_child(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    if not request.session.get('kiosk_authenticated') or request.session.get('kiosk_branch_slug') != branch_slug:
        return JsonResponse({'success': False, 'error': 'Not authorised.'}, status=403)
    try:
        data = json.loads(request.body)
        family = Family.objects.get(id=data['family_id'], branch=branch)
        first = data['first_name'].strip()
        last = data.get('last_name', '').strip()
        dob_str = data.get('date_of_birth', '')
        assert first
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid request.'})
    dob = None
    if dob_str:
        try:
            dob = date.fromisoformat(dob_str)
        except ValueError:
            pass
    child = Child.objects.create(family=family, first_name=first, last_name=last, date_of_birth=dob)
    return JsonResponse({'success': True, 'child_id': child.id, 'full_name': child.full_name})


@require_POST
def api_kiosk_delete_child(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    if not request.session.get('kiosk_authenticated') or request.session.get('kiosk_branch_slug') != branch_slug:
        return JsonResponse({'success': False, 'error': 'Not authorised.'}, status=403)
    try:
        data = json.loads(request.body)
        child = Child.objects.get(id=data['child_id'], family__branch=branch)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Child not found.'})
    child.is_active = False
    child.save(update_fields=['is_active'])
    return JsonResponse({'success': True})


# ─── Settings (staff only) ────────────────────────────────────────────────────

@staff_member_required(login_url='/admin/login/')
def settings_home(request):
    branches = Branch.objects.prefetch_related('products').all()
    return render(request, 'settings/home.html', {'branches': branches})


@staff_member_required(login_url='/admin/login/')
def settings_branch_add(request):
    if request.method == 'POST':
        try:
            branch = Branch.objects.create(
                name=request.POST['name'], slug=request.POST['slug'],
                branch_type=request.POST['branch_type'], theme=request.POST['theme'],
                icon=request.POST.get('icon', '🎟️'), description=request.POST.get('description', ''),
                kiosk_pin_hash=hash_pin(request.POST['kiosk_pin']),
                is_children_programme='is_children_programme' in request.POST,
                order=int(request.POST.get('order', 0)),
            )
            messages.success(request, f'Branch "{branch.name}" created.')
            return redirect('settings_products', branch_id=branch.id)
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return render(request, 'settings/branch_form.html', {'action': 'Add', 'branch': None})


@staff_member_required(login_url='/admin/login/')
def settings_branch_edit(request, branch_id):
    branch = get_object_or_404(Branch, id=branch_id)
    if request.method == 'POST':
        branch.name = request.POST['name']
        branch.slug = request.POST['slug']
        branch.branch_type = request.POST['branch_type']
        branch.theme = request.POST['theme']
        branch.icon = request.POST.get('icon', branch.icon)
        branch.description = request.POST.get('description', '')
        branch.is_active = 'is_active' in request.POST
        branch.is_children_programme = 'is_children_programme' in request.POST
        branch.order = int(request.POST.get('order', branch.order))
        new_pin = request.POST.get('kiosk_pin', '').strip()
        if new_pin:
            branch.kiosk_pin_hash = hash_pin(new_pin)
        branch.save()
        messages.success(request, f'Branch "{branch.name}" updated.')
        return redirect('settings_home')
    return render(request, 'settings/branch_form.html', {'action': 'Edit', 'branch': branch})


@staff_member_required(login_url='/admin/login/')
def settings_branch_delete(request, branch_id):
    branch = get_object_or_404(Branch, id=branch_id)
    if request.method == 'POST':
        branch.is_active = False
        branch.save()
        messages.success(request, f'Branch "{branch.name}" deactivated.')
    return redirect('settings_home')


@staff_member_required(login_url='/admin/login/')
def settings_products(request, branch_id):
    branch = get_object_or_404(Branch, id=branch_id)
    if request.method == 'POST':
        try:
            price_str = request.POST.get('price_aud', '').strip()
            price_aud = Decimal(price_str) if price_str else None
            Product.objects.create(
                branch=branch,
                name=request.POST['name'],
                icon=request.POST.get('icon', '🎟️'),
                credit_cost=Decimal(request.POST['credit_cost']),
                topup_bundle=int(request.POST.get('topup_bundle', 10)),
                topup_credits=int(request.POST.get('topup_credits', 10)),
                price_aud=price_aud,
                order=int(request.POST.get('order', 0)),
            )
            messages.success(request, 'Product added.')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    products = branch.products.all()
    return render(request, 'settings/products.html', {'branch': branch, 'products': products})


@staff_member_required(login_url='/admin/login/')
def settings_product_delete(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    branch_id = product.branch_id
    if request.method == 'POST':
        product.is_active = False
        product.save()
        messages.success(request, f'Product "{product.name}" deactivated.')
    return redirect('settings_products', branch_id=branch_id)