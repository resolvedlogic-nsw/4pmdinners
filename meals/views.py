import json
import csv
import qrcode
import qrcode.image.svg
import io
from decimal import Decimal
from datetime import date, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from django.conf import settings

from .models import (Branch, Product, Family, FamilyBalance, Child,
                     Transaction, QRCodeNonce, AttendanceRecord, AttendanceChild,
                     SquarePaymentOrder)
from .utils import hash_pin, check_pin, require_family_session, require_kiosk_session, get_theme_css

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────
def get_branch_or_404(slug):
    return get_object_or_404(Branch, slug=slug, is_active=True)

def branch_ctx(branch):
    return {'branch': branch, 'theme_css': get_theme_css(branch.theme)}

def get_pocket(family, branch):
    """Get the FamilyBalance pocket for this family+branch."""
    pocket, _ = FamilyBalance.objects.get_or_create(
        family=family, branch=branch, defaults={'balance': 0}
    )
    return pocket

def make_qr_svg(data: str) -> str:
    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(data, image_factory=factory, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode('utf-8')

def _site_base_url(request):
    return f"{request.scheme}://{request.get_host()}"

# ─────────────────────────────────────────────────────────────────────────────
#  Home & Branch Index
# ─────────────────────────────────────────────────────────────────────────────
def home(request):
    branches = Branch.objects.filter(is_active=True)
    return render(request, 'home.html', {'branches': branches})

def branch_index(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    return render(request, 'meals/branch_index.html', branch_ctx(branch))

# ─────────────────────────────────────────────────────────────────────────────
#  Family Auth & PIN Recovery
# ─────────────────────────────────────────────────────────────────────────────
def families_json(request, branch_slug):
    # Only return families that have interacted with this specific branch
    branch = get_branch_or_404(branch_slug)
    family_ids = FamilyBalance.objects.filter(branch=branch).values_list('family_id', flat=True)
    families = Family.objects.filter(id__in=family_ids, is_active=True).values('id', 'surname', 'display_name')
    return JsonResponse({'families': list(families)})

def family_login(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    ctx = branch_ctx(branch)
    ctx['error'] = None

    if request.method == 'POST':
        family_id = request.POST.get('family_id')
        pin = request.POST.get('pin', '')
        try:
            family = Family.objects.get(id=family_id, is_active=True)
            if check_pin(pin, family.pin_hash):
                request.session['family_id']   = family.id
                request.session['branch_slug'] = branch_slug
                return redirect('branch_user_summary', branch_slug=branch_slug)
            ctx['error'] = 'Incorrect PIN.'
        except Family.DoesNotExist:
            ctx['error'] = 'Family not found.'
        ctx['selected_family_id']   = family_id
        ctx['selected_family_name'] = request.POST.get('family_name', '')

    return render(request, 'meals/family_login.html', ctx)

def family_logout(request, branch_slug):
    request.session.flush()
    return redirect('branch_index', branch_slug=branch_slug)

def family_recover_pin(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    ctx = branch_ctx(branch)

    if request.method == 'POST':
        step = request.POST.get('step', '1')

        if step == '1':
            surname = request.POST.get('surname', '').strip()
            contact = request.POST.get('primary_contact', '').strip()
            try:
                family = Family.objects.get(surname__iexact=surname, primary_contact__iexact=contact, is_active=True)
                if not family.recovery_question:
                    ctx['error'] = 'No recovery question set. Please contact staff to reset your PIN.'
                    return render(request, 'meals/recover_pin.html', ctx)
                ctx['step'] = '2'
                ctx['family_id'] = family.id
                ctx['recovery_question'] = family.recovery_question
                return render(request, 'meals/recover_pin.html', ctx)
            except Family.DoesNotExist:
                ctx['error'] = 'No family found with those details.'

        elif step == '2':
            family_id = request.POST.get('family_id')
            answer    = request.POST.get('recovery_answer', '')
            new_pin   = request.POST.get('new_pin', '')
            confirm   = request.POST.get('confirm_pin', '')
            
            try:
                family = Family.objects.get(id=family_id, is_active=True)
                if not family.check_recovery_answer(answer):
                    ctx['step'] = '2'
                    ctx['family_id'] = family_id
                    ctx['recovery_question'] = family.recovery_question
                    ctx['error'] = 'Incorrect answer.'
                    return render(request, 'meals/recover_pin.html', ctx)
                if len(new_pin) < 4:
                    ctx['error'] = 'PIN must be at least 4 digits.'
                    ctx['step'] = '2'
                    ctx['family_id'] = family_id
                    ctx['recovery_question'] = family.recovery_question
                    return render(request, 'meals/recover_pin.html', ctx)
                if new_pin != confirm:
                    ctx['error'] = 'PINs do not match.'
                    ctx['step'] = '2'
                    ctx['family_id'] = family_id
                    ctx['recovery_question'] = family.recovery_question
                    return render(request, 'meals/recover_pin.html', ctx)
                
                family.pin_hash = hash_pin(new_pin)
                family.save(update_fields=['pin_hash'])
                messages.success(request, 'PIN reset successfully. Please log in.')
                return redirect('branch_family_login', branch_slug=branch_slug)
            except Family.DoesNotExist:
                ctx['error'] = 'Family not found.'

    ctx.setdefault('step', '1')
    return render(request, 'meals/recover_pin.html', ctx)

@require_family_session
def change_pin(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    family = get_object_or_404(Family, id=request.session['family_id'], is_active=True)
    ctx    = branch_ctx(branch)
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

@require_family_session
def family_manage_children(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    family = get_object_or_404(Family, id=request.session['family_id'], is_active=True)
    available_programmes = Branch.objects.filter(is_children_programme=True, is_active=True).order_by('order')

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            first = request.POST.get('first_name', '').strip()
            last = request.POST.get('last_name', '').strip()
            dob_str = request.POST.get('date_of_birth', '')
            prog_ids = request.POST.getlist('prog_ids')

            if first:
                dob = None
                if dob_str:
                    try:
                        dob = date.fromisoformat(dob_str)
                    except ValueError:
                        pass
                child = Child.objects.create(family=family, first_name=first, last_name=last, date_of_birth=dob)
                if prog_ids:
                    child.enrolled_branches.set(Branch.objects.filter(id__in=prog_ids))
                messages.success(request, f'{child.first_name} added successfully.')

        elif action == 'edit':
            child_id = request.POST.get('child_id')
            child = get_object_or_404(Child, id=child_id, family=family)
            child.first_name = request.POST.get('first_name', '').strip() or child.first_name
            child.last_name = request.POST.get('last_name', '').strip()
            dob_str = request.POST.get('date_of_birth', '')
            
            if dob_str:
                try:
                    child.date_of_birth = date.fromisoformat(dob_str)
                except ValueError:
                    pass
            else:
                child.date_of_birth = None
            child.save()
            
            prog_ids = request.POST.getlist('prog_ids')
            child.enrolled_branches.set(Branch.objects.filter(id__in=prog_ids))
            messages.success(request, f'{child.first_name} updated.')

        elif action == 'delete':
            child_id = request.POST.get('child_id')
            child = get_object_or_404(Child, id=child_id, family=family)
            child.is_active = False
            child.save()
            messages.success(request, f'{child.first_name} removed.')

        return redirect('branch_family_manage_children', branch_slug=branch_slug)

    ctx = branch_ctx(branch)
    ctx.update({
        'family': family,
        'children': family.children.filter(is_active=True).prefetch_related('enrolled_branches'),
        'available_programmes': available_programmes
    })
    return render(request, 'meals/family_manage_children.html', ctx)

# ─────────────────────────────────────────────────────────────────────────────
#  Family Summary & QR Flow
# ─────────────────────────────────────────────────────────────────────────────
@require_family_session
def user_summary(request, branch_slug):
    branch   = get_branch_or_404(branch_slug)
    family   = get_object_or_404(Family, id=request.session['family_id'], is_active=True)
    pocket   = get_pocket(family, branch)
    products = branch.products.filter(is_active=True)

    ctx = branch_ctx(branch)
    ctx.update({
        'family':           family,
        'pocket':           pocket,
        'products':         products,
        'all_balances':     family.balances.select_related('branch').filter(branch__is_active=True),
        'has_online_topup': products.filter(price_aud__isnull=False).exclude(price_aud=0).exists(),
    })
    if branch.is_children_programme:
        ctx['children'] = family.children.filter(is_active=True)
    return render(request, 'meals/user_summary.html', ctx)

@require_family_session
@require_POST
def generate_qr(request, branch_slug):
    branch   = get_branch_or_404(branch_slug)
    family   = get_object_or_404(Family, id=request.session['family_id'], is_active=True)
    pocket   = get_pocket(family, branch)
    products = branch.products.filter(is_active=True)

    if branch.is_children_programme:
        child_ids  = [int(x) for x in request.POST.getlist('child_ids') if x.isdigit()]
        children   = Child.objects.filter(id__in=child_ids, family=family, is_active=True)
        actual_ids = list(children.values_list('id', flat=True))
        count      = len(actual_ids)
        if count == 0:
            messages.error(request, 'Please select at least one child.')
            return redirect('branch_user_summary', branch_slug=branch_slug)
        total_cost = Decimal(count)
        if pocket.balance < total_cost:
            messages.error(request, 'Insufficient credits in this programme pocket.')
            return redirect('branch_user_summary', branch_slug=branch_slug)
        nonce = QRCodeNonce.objects.create(family=family, branch=branch, credit_units=total_cost, child_ids=actual_ids)
    else:
        total_cost         = Decimal(0)
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
        if pocket.balance < total_cost:
            messages.error(request, 'Insufficient credits in this programme pocket.')
            return redirect('branch_user_summary', branch_slug=branch_slug)
        
        product_list = [{'id': pid, 'qty': qty} for pid, qty in product_quantities.items()]
        nonce = QRCodeNonce.objects.create(family=family, branch=branch, credit_units=total_cost, child_ids=product_list)

    return redirect('branch_qr_display', branch_slug=branch_slug, nonce_id=nonce.id)

@require_family_session
def qr_display(request, branch_slug, nonce_id):
    branch = get_branch_or_404(branch_slug)
    family = get_object_or_404(Family, id=request.session['family_id'], is_active=True)
    nonce  = get_object_or_404(QRCodeNonce, id=nonce_id, family=family)
    if not nonce.is_valid():
        return render(request, 'meals/qr_expired.html', branch_ctx(branch))
    
    qr_svg = make_qr_svg(str(nonce.id))
    ctx = branch_ctx(branch)
    ctx.update({
        'nonce': nonce, 'family': family,
        'qr_svg': qr_svg, 'expires_at_iso': nonce.expires_at.isoformat(),
    })
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

# ─────────────────────────────────────────────────────────────────────────────
#  Online Top-Up (Square)
# ─────────────────────────────────────────────────────────────────────────────
@require_family_session
def topup_select(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    family = get_object_or_404(Family, id=request.session['family_id'], is_active=True)
    pocket = get_pocket(family, branch)
    online_products = branch.products.filter(is_active=True, price_aud__isnull=False).exclude(price_aud=0)

    if not online_products.exists():
        messages.info(request, 'Online top-up is not available for this programme.')
        return redirect('branch_user_summary', branch_slug=branch_slug)

    ctx = branch_ctx(branch)
    ctx.update({'family': family, 'pocket': pocket, 'online_products': online_products})
    return render(request, 'meals/topup_select.html', ctx)

@require_family_session
@require_POST
def topup_checkout(request, branch_slug):
    from .square_service import create_payment_link

    branch = get_branch_or_404(branch_slug)
    family = get_object_or_404(Family, id=request.session['family_id'], is_active=True)

    total_aud      = Decimal(0)
    credits_to_add = Decimal(0)
    cart_items     = []
    summary_parts  = []

    for key, value in request.POST.items():
        if key.startswith('qty_'):
            try:
                qty = int(value)
                if qty > 0:
                    product_id = int(key.replace('qty_', ''))
                    product    = get_object_or_404(Product, id=product_id, branch=branch, is_active=True)
                    if product.available_online:
                        line_aud       = product.price_aud * qty
                        line_credits   = Decimal(product.topup_credits) * qty
                        total_aud     += line_aud
                        credits_to_add += line_credits
                        cart_items.append({
                            'name':             f"{product.name} ({product.topup_bundle} credits)",
                            'quantity':         str(qty),
                            'unit_price_cents': int(product.price_aud * 100),
                        })
                        summary_parts.append(f"{qty}× {product.name}")
            except (ValueError, TypeError):
                pass

    if not cart_items:
        messages.error(request, 'Please select at least one product.')
        return redirect('branch_topup_select', branch_slug=branch_slug)

    cart_summary = ', '.join(summary_parts)

    order = SquarePaymentOrder.objects.create(
        family=family,
        branch=branch,
        credits_to_add=credits_to_add,
        amount_aud=total_aud,
        cart_summary=cart_summary,
        cart_data=cart_items,
    )

    base        = _site_base_url(request)
    success_url = f"{base}/{branch_slug}/topup/success/?order={order.id}"
    cancel_url  = f"{base}/{branch_slug}/topup/cancel/"

    try:
        link_url, square_order_id, link_id = create_payment_link(order, success_url, cancel_url)
        order.square_order_id        = square_order_id
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
    from .square_service import verify_payment

    branch   = get_branch_or_404(branch_slug)
    family   = get_object_or_404(Family, id=request.session['family_id'], is_active=True)
    order_id = request.GET.get('order')

    try:
        order = SquarePaymentOrder.objects.get(id=order_id, family=family)
    except SquarePaymentOrder.DoesNotExist:
        messages.error(request, 'Order not found.')
        return redirect('branch_user_summary', branch_slug=branch_slug)

    if order.status == 'completed':
        ctx = branch_ctx(branch)
        ctx.update({'family': family, 'order': order, 'pocket': get_pocket(family, branch), 'already_processed': True})
        return render(request, 'meals/topup_success.html', ctx)

    paid = verify_payment(order.square_order_id) if order.square_order_id else False

    if paid:
        target_branch  = order.branch or branch
        pocket         = get_pocket(family, target_branch)
        pocket.balance += order.credits_to_add
        pocket.save(update_fields=['balance'])

        Transaction.objects.create(
            family=family,
            branch=target_branch,
            credit_delta=order.credits_to_add,
            reason='online_topup',
            performed_by='square_online',
            notes=(f"Square online: {order.cart_summary} "
                   f"(${order.amount_aud} AUD) → +{order.credits_to_add} credits"),
        )
        order.status       = 'completed'
        order.completed_at = timezone.now()
        order.save(update_fields=['status', 'completed_at'])

        ctx = branch_ctx(branch)
        ctx.update({'family': family, 'order': order, 'pocket': pocket, 'already_processed': False})
        return render(request, 'meals/topup_success.html', ctx)
    else:
        ctx = branch_ctx(branch)
        ctx.update({'family': family, 'order': order, 'pocket': get_pocket(family, branch), 'payment_pending': True})
        return render(request, 'meals/topup_success.html', ctx)

@require_family_session
def topup_cancel(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    messages.info(request, 'Payment cancelled — no charge was made.')
    return redirect('branch_user_summary', branch_slug=branch_slug)

@csrf_exempt
@require_POST
def topup_webhook(request, branch_slug):
    try:
        payload    = json.loads(request.body)
        event_type = payload.get('type', '')

        if event_type == 'payment.completed':
            payment     = payload.get('data', {}).get('object', {}).get('payment', {})
            sq_order_id = payment.get('order_id', '')

            try:
                order = SquarePaymentOrder.objects.get(square_order_id=sq_order_id, status='pending')
            except SquarePaymentOrder.DoesNotExist:
                return HttpResponse(status=200)

            order.square_payment_id = payment.get('id', '')
            order.save(update_fields=['square_payment_id'])

            family        = order.family
            target_branch = order.branch
            
            if target_branch:
                pocket         = get_pocket(family, target_branch)
                pocket.balance += order.credits_to_add
                pocket.save(update_fields=['balance'])

                Transaction.objects.create(
                    family=family,
                    branch=target_branch,
                    credit_delta=order.credits_to_add,
                    reason='online_topup',
                    performed_by='square_online',
                    notes=(f"Square webhook: {order.cart_summary} "
                           f"(${order.amount_aud} AUD) → +{order.credits_to_add} credits"),
                )
                order.status       = 'completed'
                order.completed_at = timezone.now()
                order.save(update_fields=['status', 'completed_at'])
    except Exception:
        pass 

    return HttpResponse(status=200)

# ─────────────────────────────────────────────────────────────────────────────
#  Kiosk Auth & Views
# ─────────────────────────────────────────────────────────────────────────────
def kiosk_login(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    ctx    = branch_ctx(branch)
    if request.method == 'POST':
        pin = request.POST.get('pin', '')
        if check_pin(pin, branch.kiosk_pin_hash):
            request.session['kiosk_authenticated'] = True
            request.session['kiosk_branch_slug']   = branch_slug
            return redirect('branch_kiosk_home', branch_slug=branch_slug)
        ctx['error'] = 'Incorrect kiosk PIN.'
    return render(request, 'meals/kiosk_login.html', ctx)

@require_kiosk_session
def kiosk_home(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    today = timezone.localdate()
    ctx = branch_ctx(branch)
    ctx.update({
        'seven_days_ago': today - timedelta(days=7),
        'start_of_month': today.replace(day=1),
    })
    return render(request, 'meals/kiosk_home.html', ctx)

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
    branch   = get_branch_or_404(branch_slug)
    balances = FamilyBalance.objects.filter(branch=branch, family__is_active=True).select_related('family').order_by('family__surname')
    ctx = branch_ctx(branch)
    ctx['balances'] = balances
    return render(request, 'meals/kiosk_manual.html', ctx)

@require_kiosk_session
def kiosk_family_detail(request, branch_slug, family_id):
    branch = get_branch_or_404(branch_slug)
    family = get_object_or_404(Family, id=family_id, is_active=True)
    pocket = get_pocket(family, branch)
    ctx    = branch_ctx(branch)
    ctx.update({
        'family':              family,
        'pocket':              pocket,
        'products':            branch.products.filter(is_active=True),
        'recent_transactions': Transaction.objects.filter(family=family, branch=branch).order_by('-timestamp')[:10],
    })
    if branch.is_children_programme:
        ctx['children'] = family.children.filter(is_active=True)
    return render(request, 'meals/kiosk_family_detail.html', ctx)

@require_kiosk_session
def kiosk_manage_children(request, branch_slug, family_id):
    branch = get_branch_or_404(branch_slug)
    family = get_object_or_404(Family, id=family_id, is_active=True)
    ctx    = branch_ctx(branch)
    ctx.update({
        'family': family, 
        'children': family.children.prefetch_related('enrolled_branches').all(),
        'available_programmes': Branch.objects.filter(is_children_programme=True, is_active=True).order_by('order')
    })
    return render(request, 'meals/kiosk_manage_children.html', ctx)

@require_kiosk_session
def kiosk_bulk_checkin(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    
    # Get all kids explicitly enrolled in THIS branch
    children = Child.objects.filter(enrolled_branches=branch, is_active=True).select_related('family').order_by('family__surname', 'first_name')

    if request.method == 'POST':
        child_ids = [int(x) for x in request.POST.getlist('child_ids') if x.isdigit()]
        notes = request.POST.get('notes', '').strip()

        if child_ids:
            # Group by family so siblings are on the same attendance record
            selected_children = Child.objects.filter(id__in=child_ids).select_related('family')
            family_groups = {}
            for child in selected_children:
                family_groups.setdefault(child.family, []).append(child)

            for family, kids in family_groups.items():
                record = AttendanceRecord.objects.create(
                    branch=branch, family=family, session_date=timezone.localdate(),
                    transaction=None, notes=notes
                )
                for child in kids:
                    AttendanceChild.objects.create(record=record, child=child)

            messages.success(request, f'Successfully checked in {len(child_ids)} children.')
            
        elif notes:
            # The "Guest Dilemma" Fix: If they only typed notes, assign it to a generic Guest family
            guest_family, _ = Family.objects.get_or_create(
                surname=" Guest", defaults={'primary_contact': 'Visitor', 'display_name': 'Guest / Visitor', 'pin_hash': hash_pin('0000')}
            )
            AttendanceRecord.objects.create(
                branch=branch, family=guest_family, session_date=timezone.localdate(),
                transaction=None, notes=notes
            )
            messages.success(request, 'Guest notes saved successfully.')
            
        else:
            messages.error(request, 'No children selected and no notes entered.')
            
        return redirect('branch_kiosk_home', branch_slug=branch_slug)

    ctx = branch_ctx(branch)
    ctx['children'] = children
    return render(request, 'meals/kiosk_bulk_checkin.html', ctx)

@require_kiosk_session
def kiosk_view_attendance(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    date_str = request.GET.get('date', str(timezone.localdate()))
    
    try:
        session_date = date.fromisoformat(date_str)
    except ValueError:
        session_date = timezone.localdate()

    # Fetch records and prefetch the children to avoid N+1 database queries
    records = AttendanceRecord.objects.filter(
        branch=branch, session_date=session_date
    ).select_related('family').prefetch_related('children_present__child').order_by('-timestamp')

    ctx = branch_ctx(branch)
    ctx.update({
        'session_date': session_date,
        'records': records,
    })
    return render(request, 'meals/kiosk_view_attendance.html', ctx)

# ─────────────────────────────────────────────────────────────────────────────
#  Kiosk Exports
# ─────────────────────────────────────────────────────────────────────────────
@require_kiosk_session
def kiosk_export_attendance(request, branch_slug):
    branch           = get_branch_or_404(branch_slug)
    session_date_str = request.GET.get('date', str(date.today()))
    try:
        session_date = date.fromisoformat(session_date_str)
    except ValueError:
        session_date = date.today()
    records  = AttendanceRecord.objects.filter(branch=branch, session_date=session_date).prefetch_related('children_present__child', 'family')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{branch_slug}_attendance_{session_date}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Family', 'Primary Contact', 'Child', 'Check-in Time'])
    
    for record in records:
        for cp in record.children_present.all():
            writer.writerow([record.family.display_name, record.family.primary_contact, cp.child.full_name, record.timestamp.strftime('%H:%M')])
    return response

@require_kiosk_session
def kiosk_export_roster(request, branch_slug):
    branch   = get_branch_or_404(branch_slug)
    balances = FamilyBalance.objects.filter(branch=branch, family__is_active=True).select_related('family').prefetch_related('family__children')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{branch_slug}_roster.csv"'
    writer   = csv.writer(response)
    writer.writerow(['Family', 'Primary Contact', 'Balance', 'Child First Name', 'Child Last Name', 'DOB', 'Active'])
    
    for bal in balances:
        family = bal.family
        children = family.children.all()
        if children:
            for child in children:
                writer.writerow([family.display_name, family.primary_contact, bal.balance, child.first_name, child.last_name, child.date_of_birth or '', 'Yes' if child.is_active else 'No'])
        else:
            writer.writerow([family.display_name, family.primary_contact, bal.balance, '', '', '', ''])
    return response

@require_kiosk_session
def kiosk_export_transactions(request, branch_slug):
    branch    = get_branch_or_404(branch_slug)
    today     = timezone.localdate()
    start_str = request.GET.get('start')
    end_str   = request.GET.get('end')
    
    start_date = date.fromisoformat(start_str) if start_str else today
    end_date   = date.fromisoformat(end_str)   if end_str   else today

    txns = Transaction.objects.filter(branch=branch, timestamp__date__range=[start_date, end_date]).select_related('family').order_by('-timestamp')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{branch_slug}_transactions_{start_date}_to_{end_date}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Date/Time', 'Family', 'Credits (Delta)', 'Reason', 'Handled By', 'Notes'])
    
    for t in txns:
        writer.writerow([
            timezone.localtime(t.timestamp).strftime('%d/%m/%Y %H:%M'),
            t.family.display_name,
            t.credit_delta,
            t.get_reason_display(),
            t.get_performed_by_display(),
            t.notes,
        ])
    return response

# ─────────────────────────────────────────────────────────────────────────────
#  API: Kiosk Actions
# ─────────────────────────────────────────────────────────────────────────────
@require_POST
def api_redeem_qr(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    if not request.session.get('kiosk_authenticated') or request.session.get('kiosk_branch_slug') != branch_slug:
        return JsonResponse({'success': False, 'error': 'Not authorised.'}, status=403)

    try:
        payload  = json.loads(request.body)
        nonce_id = payload.get('payload') or payload.get('nonce_id')
        nonce    = QRCodeNonce.objects.select_related('family').get(id=nonce_id)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid QR code.'})

    if nonce.branch_id and nonce.branch_id != branch.id:
        return JsonResponse({'success': False, 'error': 'QR code is for a different branch.'})
    if not nonce.is_valid():
        return JsonResponse({'success': False, 'error': 'QR code has expired or already been used.'})

    family = nonce.family
    pocket = get_pocket(family, branch)

    if pocket.balance < nonce.credit_units:
        return JsonResponse({'success': False, 'error': 'Insufficient credits.'})

    pocket.balance -= nonce.credit_units
    pocket.save(update_fields=['balance'])

    txn = Transaction.objects.create(family=family, branch=branch, credit_delta=-nonce.credit_units, reason='qr_redemption', performed_by='system_qr')
    nonce.used = True
    nonce.save(update_fields=['used'])

    response_data = {
        'success':          True,
        'family_name':      family.display_name,
        'credits_deducted': float(nonce.credit_units),
        'new_balance':      float(pocket.balance),
    }

    if branch.is_children_programme and nonce.child_ids:
        child_ids = [x for x in nonce.child_ids if isinstance(x, int)]
        if child_ids:
            record   = AttendanceRecord.objects.create(branch=branch, family=family, session_date=timezone.localdate(), transaction=txn)
            children = Child.objects.filter(id__in=child_ids, family=family)
            for child in children:
                AttendanceChild.objects.create(record=record, child=child)
            response_data['children_checked_in'] = [c.full_name for c in children]

    return JsonResponse(response_data)

@require_POST
def api_kiosk_deduct(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    if not request.session.get('kiosk_authenticated') or request.session.get('kiosk_branch_slug') != branch_slug:
        return JsonResponse({'success': False, 'error': 'Not authorised.'}, status=403)

    try:
        data   = json.loads(request.body)
        family = Family.objects.get(id=data['family_id'], is_active=True)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid request.'})

    pocket = get_pocket(family, branch)

    if branch.is_children_programme:
        child_ids  = [int(x) for x in data.get('child_ids', []) if str(x).isdigit()]
        count      = len(child_ids)
        if count == 0:
            return JsonResponse({'success': False, 'error': 'No children selected.'})
        total_cost = Decimal(count)
    else:
        products   = branch.products.filter(is_active=True)
        total_cost = Decimal(0)
        for product in products:
            qty = int(data.get(f'qty_{product.id}', 0))
            total_cost += product.credit_cost * qty

    notes_input = data.get('notes', '').strip()

    # THE BYPASS: Free Sunday School route
    if branch.is_children_programme and total_cost == 0:
        if not child_ids:
            return JsonResponse({'success': False, 'error': 'No children selected.'})
            
        record = AttendanceRecord.objects.create(
            branch=branch, family=family, session_date=timezone.localdate(), 
            transaction=None, notes=notes_input # <--- Notes saved here!
        )
        children = Child.objects.filter(id__in=child_ids, family=family)
        for child in children:
            AttendanceChild.objects.create(record=record, child=child)
            
        return JsonResponse({'success': True, 'family_name': family.display_name, 'credits_deducted': 0, 'new_balance': float(pocket.balance)})

    # THE STANDARD: Paid Dinners/Coffee route
    if total_cost <= 0:
        return JsonResponse({'success': False, 'error': 'Nothing to deduct.'})
    if pocket.balance < total_cost:
        return JsonResponse({'success': False, 'error': 'Insufficient credits.'})

    pocket.balance -= total_cost
    pocket.save(update_fields=['balance'])

    txn = Transaction.objects.create(family=family, branch=branch, credit_delta=-total_cost, reason='manual_kiosk', performed_by='kiosk_volunteer', notes=notes_input)

    if branch.is_children_programme and child_ids:
        record = AttendanceRecord.objects.create(branch=branch, family=family, session_date=timezone.localdate(), transaction=txn, notes=notes_input)
        children = Child.objects.filter(id__in=child_ids, family=family)
        for child in children:
            AttendanceChild.objects.create(record=record, child=child)

    return JsonResponse({'success': True, 'family_name': family.display_name, 'credits_deducted': float(total_cost), 'new_balance': float(pocket.balance)})

@require_POST
def api_kiosk_topup(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    if not request.session.get('kiosk_authenticated') or request.session.get('kiosk_branch_slug') != branch_slug:
        return JsonResponse({'success': False, 'error': 'Not authorised.'}, status=403)

    try:
        data   = json.loads(request.body)
        family = Family.objects.get(id=data['family_id'], is_active=True)
        amount = Decimal(str(data['amount']))
        assert amount > 0
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid request.'})

    pocket         = get_pocket(family, branch)
    pocket.balance += amount
    pocket.save(update_fields=['balance'])

    Transaction.objects.create(family=family, branch=branch, credit_delta=amount, reason='credit_top_up', performed_by='kiosk_volunteer', notes=data.get('notes', ''))
    return JsonResponse({'success': True, 'new_balance': float(pocket.balance)})

@require_POST
def api_kiosk_add_family(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    if not request.session.get('kiosk_authenticated') or request.session.get('kiosk_branch_slug') != branch_slug:
        return JsonResponse({'success': False, 'error': 'Not authorised.'}, status=403)

    try:
        data    = json.loads(request.body)
        surname = data['surname'].strip()
        contact = data['primary_contact'].strip()
        pin     = data['pin'].strip()
        display = data.get('display_name', '').strip() or f"{surname} — {contact}"
        assert surname and contact and len(pin) >= 4
    except Exception:
        return JsonResponse({'success': False, 'error': 'Please fill all fields (PIN must be ≥4 digits).'})

    if Family.objects.filter(surname__iexact=surname, primary_contact__iexact=contact).exists():
        return JsonResponse({'success': False, 'error': 'A family with that surname and contact already exists.'})

    family = Family.objects.create(surname=surname, primary_contact=contact, display_name=display, pin_hash=hash_pin(pin))
    return JsonResponse({'success': True, 'family_id': family.id})

@require_POST
def api_kiosk_add_child(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    if not request.session.get('kiosk_authenticated') or request.session.get('kiosk_branch_slug') != branch_slug:
        return JsonResponse({'success': False, 'error': 'Not authorised.'}, status=403)

    try:
        data    = json.loads(request.body)
        family  = Family.objects.get(id=data['family_id'], is_active=True)
        first   = data['first_name'].strip()
        last    = data.get('last_name', '').strip()
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
            
    # NEW: Grab the branch IDs from the request
    branch_ids = data.get('branch_ids', [])
    
    child = Child.objects.create(family=family, first_name=first, last_name=last, date_of_birth=dob)
    
    # NEW: Link the child to the selected programmes
    if branch_ids:
        child.enrolled_branches.set(Branch.objects.filter(id__in=branch_ids))
        
    return JsonResponse({'success': True, 'child_id': child.id, 'full_name': child.full_name})

@require_POST
def api_kiosk_delete_child(request, branch_slug):
    branch = get_branch_or_404(branch_slug)
    if not request.session.get('kiosk_authenticated') or request.session.get('kiosk_branch_slug') != branch_slug:
        return JsonResponse({'success': False, 'error': 'Not authorised.'}, status=403)

    try:
        data  = json.loads(request.body)
        child = Child.objects.get(id=data['child_id'], family__is_active=True)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Child not found.'})

    child.is_active = False
    child.save(update_fields=['is_active'])
    return JsonResponse({'success': True})

# ─────────────────────────────────────────────────────────────────────────────
#  Settings (Staff Only)
# ─────────────────────────────────────────────────────────────────────────────
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
        branch.name                  = request.POST['name']
        branch.slug                  = request.POST['slug']
        branch.branch_type           = request.POST['branch_type']
        branch.theme                 = request.POST['theme']
        branch.icon                  = request.POST.get('icon', branch.icon)
        branch.description           = request.POST.get('description', '')
        branch.is_active             = 'is_active' in request.POST
        branch.is_children_programme = 'is_children_programme' in request.POST
        branch.order                 = int(request.POST.get('order', branch.order))
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
    product   = get_object_or_404(Product, id=product_id)
    branch_id = product.branch_id
    if request.method == 'POST':
        product.is_active = False
        product.save()
        messages.success(request, f'Product "{product.name}" deactivated.')
    return redirect('settings_products', branch_id=branch_id)  