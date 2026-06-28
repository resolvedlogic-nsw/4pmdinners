# store/views.py
import json
import uuid
import os
import square.client as square_module
from square.client import Client
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages

from .data import PRODUCTS, CATEGORIES, SIZE_CHARTS, COLOUR_HEX


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_square_client():
    return Client(
        access_token=os.environ.get('SQUARE_ACCESS_TOKEN'),
        environment=os.environ.get('SQUARE_ENVIRONMENT', 'production'),
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

    # Attach first available colour/image for card preview
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

    # Find existing matching line
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
    """Update qty or remove a line. Expects JSON {index, qty} where qty=0 removes."""
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

        # Build Square line items
        line_items = []
        note_parts = []
        for item in cart:
            desc = f"{item['name']} – {item['colour']}, Size {item['size']}"
            note_parts.append(f"{item['qty']}x {desc}")
            line_items.append({
                'name': desc,
                'quantity': str(item['qty']),
                'base_price_money': {
                    'amount': int(item['price'] * 100),  # cents
                    'currency': 'AUD',
                },
            })

        order_note = f"Order for {name} ({email})"
        if notes:
            order_note += f". Notes: {notes}"
        order_note += ". Items: " + "; ".join(note_parts)

        idempotency_key = str(uuid.uuid4())
        location_id = os.environ.get('SQUARE_LOCATION_ID')

        # Store buyer info in session for success page
        request.session['store_buyer'] = {'name': name, 'email': email}

        try:
            client = get_square_client()
            result = client.checkout.create_payment_link({
                'idempotency_key': idempotency_key,
                'order': {
                    'order': {
                        'location_id': location_id,
                        'line_items': line_items,
                        'metadata': {
                            'buyer_name': name,
                            'buyer_email': email,
                        },
                    },
                },
                'checkout_options': {
                    'redirect_url': request.build_absolute_uri('/store/success/'),
                    'merchant_support_email': email,
                },
                'pre_populated_data': {
                    'buyer_email': email,
                },
            })

            if result.is_success():
                payment_link = result.body['payment_link']
                save_cart(request, [])  # clear cart on redirect
                return redirect(payment_link['url'])
            else:
                errors = result.errors
                error_msg = '; '.join(e.get('detail', 'Unknown error') for e in errors)
                messages.error(request, f'Payment could not be started: {error_msg}')

        except Exception as e:
            messages.error(request, f'An error occurred: {str(e)}')

    return render(request, 'store/checkout.html', {
        'cart': cart,
        'cart_count': sum(i['qty'] for i in cart),
        **totals,
    })


# ---------------------------------------------------------------------------
# Success / Cancel
# ---------------------------------------------------------------------------

def order_success(request):
    buyer = request.session.pop('store_buyer', {})
    return render(request, 'store/success.html', {
        'buyer': buyer,
        'cart_count': 0,
    })


def order_cancel(request):
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
