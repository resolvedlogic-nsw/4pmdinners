# store/views.py
import json
import uuid
import os
from square.client import Square, SquareEnvironment
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required

from .data import PRODUCTS, CATEGORIES, SIZE_CHARTS, COLOUR_HEX
from .models import Order, OrderItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_square_client():
    env = os.environ.get('SQUARE_ENVIRONMENT', 'production').lower()
    square_env = SquareEnvironment.PRODUCTION if env == 'production' else SquareEnvironment.SANDBOX
    return Square(
        token=os.environ.get('SQUARE_ACCESS_TOKEN'),
        environment=square_env,
    )


def get_cart(request):
    return request.session.get('store_cart', [])


def save_cart(request, cart):
    request.session['store_cart'] = cart
    request.session.modified = True


def cart_totals(cart):
    subtotal = sum(item['price'] * item['qty'] for item in cart)
    return {'subtotal': subtotal, 'total': subtotal}


# ---------------------------------------------------------------------------
# Product listing
# ---------------------------------------------------------------------------

def product_list(request):
    grouped = {}
    for cat_slug, cat_name in CATEGORIES:
        items = [
            {'slug': slug, **prod}
            for slug, prod in PRODUCTS.items()
            if prod['category'] == cat_slug
        ]
        if items:
            grouped[cat_name] = items

    for cat_name, items in grouped.items():
        for item in items:
            variants = item['variants']
            if variants:
                first_colour = next(iter(variants))
                item['preview_image'] = variants[first_colour]['image']
                item['preview_colour'] = first_colour
                item['price_from'] = min(v['price'] for v in variants.values())
            else:
                item['preview_image'] = None
                item['price_from'] = None

    cart = get_cart(request)
    cart_count = sum(i['qty'] for i in cart)

    return render(request, 'store/product_list.html', {
        'grouped': grouped,
        'cart_count': cart_count,
    })


# ---------------------------------------------------------------------------
# Product detail
# ---------------------------------------------------------------------------

def product_detail(request, slug):
    if slug not in PRODUCTS:
        from django.http import Http404
        raise Http404

    product = PRODUCTS[slug]
    colour_hex = {c: COLOUR_HEX.get(c, '#888') for c in product['variants']}
    cart = get_cart(request)
    cart_count = sum(i['qty'] for i in cart)

    return render(request, 'store/product_detail.html', {
        'slug': slug,
        'product': product,
        'colour_hex': colour_hex,
        'colour_hex_json': json.dumps(colour_hex),
        'variants_json': json.dumps(product['variants']),
        'sizes': product['sizes'],
        'cart_count': cart_count,
    })


# ---------------------------------------------------------------------------
# Cart operations (AJAX)
# ---------------------------------------------------------------------------

@require_POST
def cart_add(request):
    try:
        data = json.loads(request.body)
        slug = data.get('slug')
        colour = data.get('colour')
        size = data.get('size')
        qty = int(data.get('qty', 1))
    except (ValueError, KeyError):
        return JsonResponse({'ok': False, 'error': 'Invalid data'}, status=400)

    if slug not in PRODUCTS:
        return JsonResponse({'ok': False, 'error': 'Unknown product'}, status=400)

    product = PRODUCTS[slug]
    if colour not in product['variants']:
        return JsonResponse({'ok': False, 'error': 'Colour not available'}, status=400)
    if size not in product['sizes']:
        return JsonResponse({'ok': False, 'error': 'Size not available'}, status=400)

    variant = product['variants'][colour]
    cart = get_cart(request)

    for item in cart:
        if item['slug'] == slug and item['colour'] == colour and item['size'] == size:
            item['qty'] += qty
            save_cart(request, cart)
            cart_count = sum(i['qty'] for i in cart)
            return JsonResponse({'ok': True, 'cart_count': cart_count})

    cart.append({
        'slug': slug,
        'name': product['name'],
        'colour': colour,
        'size': size,
        'price': variant['price'],
        'image': variant['image'],
        'qty': qty,
    })
    save_cart(request, cart)
    cart_count = sum(i['qty'] for i in cart)
    return JsonResponse({'ok': True, 'cart_count': cart_count})


@require_POST
def cart_update(request):
    try:
        data = json.loads(request.body)
        index = int(data.get('index'))
        qty = int(data.get('qty', 0))
    except (ValueError, TypeError):
        return JsonResponse({'ok': False}, status=400)

    cart = get_cart(request)
    if index < 0 or index >= len(cart):
        return JsonResponse({'ok': False}, status=400)

    if qty <= 0:
        cart.pop(index)
    else:
        cart[index]['qty'] = qty

    save_cart(request, cart)
    totals = cart_totals(cart)
    cart_count = sum(i['qty'] for i in cart)
    return JsonResponse({'ok': True, 'cart_count': cart_count, **totals})


# ---------------------------------------------------------------------------
# Cart page
# ---------------------------------------------------------------------------

def cart_view(request):
    cart = get_cart(request)
    totals = cart_totals(cart)
    return render(request, 'store/cart.html', {
        'cart': cart,
        'cart_count': sum(i['qty'] for i in cart),
        **totals,
    })


# ---------------------------------------------------------------------------
# Checkout → Square redirect
# ---------------------------------------------------------------------------

def checkout(request):
    cart = get_cart(request)
    if not cart:
        return redirect('store:product_list')

    totals = cart_totals(cart)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        notes = request.POST.get('notes', '').strip()

        if not name or not email:
            messages.error(request, 'Please enter your name and email.')
            return render(request, 'store/checkout.html', {
                'cart': cart,
                'cart_count': sum(i['qty'] for i in cart),
                **totals,
            })

        # --- Persist the order locally FIRST, before Square is involved at all.
        # This is our source of truth — Square is just the payment rail.
        order = Order.objects.create(name=name, email=email, notes=notes, status=Order.STATUS_PENDING)
        for item in cart:
            OrderItem.objects.create(
                order=order,
                product_slug=item['slug'],
                product_name=item['name'],
                colour=item['colour'],
                size=item['size'],
                price=item['price'],
                qty=item['qty'],
            )

        # Build Square line items
        line_items = []
        for item in cart:
            desc = f"{item['name']} – {item['colour']}, Size {item['size']}"
            line_items.append({
                'name': desc,
                'quantity': str(item['qty']),
                'base_price_money': {
                    'amount': int(item['price'] * 100),
                    'currency': 'AUD',
                },
            })

        location_id = os.environ.get('SQUARE_LOCATION_ID')
        request.session['store_order_id'] = order.id

        try:
            client = get_square_client()
            result = client.checkout.payment_links.create(
                idempotency_key=str(uuid.uuid4()),
                order={
                    'location_id': location_id,
                    'line_items': line_items,
                    'metadata': {
                        'buyer_name': name,
                        'buyer_email': email,
                        'local_order_id': str(order.id),
                    },
                },
                checkout_options={
                    'redirect_url': request.build_absolute_uri('/store/success/'),
                },
                pre_populated_data={
                    'buyer_email': email,
                },
            )

            url = result.payment_link.url
            order.square_payment_link_id = getattr(result.payment_link, 'id', '') or ''
            order.square_order_id = getattr(result.payment_link, 'order_id', '') or ''
            order.save(update_fields=['square_payment_link_id', 'square_order_id'])

            save_cart(request, [])
            return redirect(url)

        except Exception as e:
            # Payment link failed — the order record stays as 'pending' so nothing
            # is lost, but flag it clearly for review.
            order.notes = (order.notes + f"\n[Payment link creation failed: {e}]").strip()
            order.save(update_fields=['notes'])
            messages.error(request, f'Payment could not be started: {str(e)}')

    return render(request, 'store/checkout.html', {
        'cart': cart,
        'cart_count': sum(i['qty'] for i in cart),
        **totals,
    })


# ---------------------------------------------------------------------------
# Success / Cancel
# ---------------------------------------------------------------------------

def order_success(request):
    order_id = request.session.pop('store_order_id', None)
    order = None
    if order_id:
        order = Order.objects.filter(id=order_id).first()
        if order and order.status == Order.STATUS_PENDING:
            order.status = Order.STATUS_PAID
            order.save(update_fields=['status'])

    buyer = {'name': order.name, 'email': order.email} if order else {}
    return render(request, 'store/success.html', {
        'buyer': buyer,
        'cart_count': 0,
    })


def order_cancel(request):
    order_id = request.session.get('store_order_id')
    if order_id:
        Order.objects.filter(id=order_id, status=Order.STATUS_PENDING).update(status=Order.STATUS_CANCELLED)

    return render(request, 'store/cancel.html', {
        'cart_count': sum(i['qty'] for i in get_cart(request)),
    })


# ---------------------------------------------------------------------------
# Size chart
# ---------------------------------------------------------------------------

def size_chart(request):
    cart = get_cart(request)
    return render(request, 'store/size_chart.html', {
        'size_charts': SIZE_CHARTS,
        'cart_count': sum(i['qty'] for i in cart),
    })


# ---------------------------------------------------------------------------
# Order report (staff only)
# ---------------------------------------------------------------------------

@staff_member_required
def order_report(request):
    status_filter = request.GET.get('status', 'paid')

    orders = Order.objects.prefetch_related('items').all()
    if status_filter in ('paid', 'pending', 'cancelled'):
        orders = orders.filter(status=status_filter)
    # status_filter == 'all' -> no filter

    rows = []
    for order in orders:
        for item in order.items.all():
            rows.append({
                'order_id': order.id,
                'date': order.created_at,
                'buyer_name': order.name,
                'buyer_email': order.email,
                'status': order.status,
                'product_name': item.product_name,
                'colour': item.colour,
                'size': item.size,
                'qty': item.qty,
                'price': item.price,
                'subtotal': item.subtotal,
            })

    grand_total = sum(r['subtotal'] for r in rows)

    return render(request, 'store/report.html', {
        'rows': rows,
        'status_filter': status_filter,
        'grand_total': grand_total,
        'cart_count': sum(i['qty'] for i in get_cart(request)),
    })
