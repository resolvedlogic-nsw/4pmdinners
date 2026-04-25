"""
square_service.py
Thin wrapper around the Square Payments API.
All Square-specific logic lives here so views stay clean.
"""
import uuid
from decimal import Decimal
from django.conf import settings


def _get_client():
    from square.client import Client
    return Client(
        access_token=settings.SQUARE_ACCESS_TOKEN,
        environment=settings.SQUARE_ENVIRONMENT,  # 'sandbox' or 'production'
    )


def create_payment_link(order_record, success_url, cancel_url):
    """
    Creates a Square hosted payment link for a SquarePaymentOrder.
    Returns (payment_link_url, order_id, payment_link_id) on success.
    Raises Exception with message on failure.

    Square line items ensure the receipt and reports show:
      - Product name (e.g. "Adult Meal Bundle x10")
      - Quantity purchased
      - Unit price and total
    """
    client = _get_client()

    # Build the line items dynamically from the cart data
    line_items = []
    for item in order_record.cart_data:
        line_items.append({
            'name': item['name'],
            'quantity': item['quantity'],
            'base_price_money': {
                'amount': item['unit_price_cents'],
                'currency': 'AUD',
            },
            'note': f"Branch: {order_record.family.branch.name} | Family: {order_record.family.display_name}",
        })

    body = {
        'idempotency_key': str(order_record.id),  # our UUID prevents duplicate charges
        'order': {
            'location_id': settings.SQUARE_LOCATION_ID,
            'reference_id': str(order_record.id),   # our internal order ID on Square reports
            'line_items': line_items,
            'metadata': {
                'order_uuid':   str(order_record.id),
                'family_id':    str(order_record.family_id),
                'branch_slug':  order_record.family.branch.slug,
            },
        },
        'checkout_options': {
            'redirect_url':          success_url,
            'ask_for_shipping_address': False,
        },
        'pre_populated_data': {
            'buyer_email': '',  # could populate if families have emails in future
        },
    }

    result = client.checkout.create_payment_link(body=body)

    if result.is_success():
        link = result.body['payment_link']
        return (
            link['url'],
            link.get('order_id', ''),
            link['id'],
        )
    else:
        errors = result.errors
        msg = '; '.join(e.get('detail', e.get('code', 'Unknown error')) for e in errors)
        raise Exception(f"Square error: {msg}")


def verify_payment(square_order_id):
    """
    Checks Square to confirm a payment has been completed for a given order_id.
    Returns True if paid, False otherwise.
    """
    client = _get_client()
    result = client.orders.retrieve_order(order_id=square_order_id)

    if result.is_success():
        order = result.body.get('order', {})
        state = order.get('state', '')
        # Square order states: OPEN, COMPLETED, CANCELED
        return state == 'COMPLETED'
    return False