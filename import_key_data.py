"""
Batch-imports PatternRule and ItemPrice rows from keypattern.csv / keyitem.csv.

Run from the project root (same folder as manage.py):

    python import_key_data.py

Expects keypattern.csv and keyitem.csv to be in the same folder you run
this from, unless you change the paths below.
"""

import csv
import os
from decimal import Decimal, InvalidOperation

import django

# --- Point this at your actual settings module if it's not 'config.settings' ---
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from finances.models import ItemPrice, PatternRule  # noqa: E402  (must come after django.setup())


def import_pattern_rules(path='keypattern.csv'):
    print("Importing Pattern Rules...")
    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            name = (row.get('Name') or '').strip()
            pattern = (row.get('Pattern') or '').strip()
            if not name or not pattern:
                print(f"  Skipped row {i + 1}: missing Name or Pattern.")
                continue

            rule, created = PatternRule.objects.get_or_create(
                name=name,
                defaults={
                    'pattern': pattern,
                    'fixed_ministry': (row.get('Categories') or '').strip(),
                    # Space priorities out (10, 20, 30...) to leave room for
                    # inserting new rules later without renumbering everything.
                    'priority': (i + 1) * 10,
                    'active': True,
                }
            )
            if created:
                print(f"  Added pattern: {rule.name}")
            else:
                print(f"  Already exists, skipped: {rule.name}")


def import_item_prices(path='keyitem.csv'):
    print("\nImporting Item Prices...")
    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            item_name = (row.get('Product') or '').strip()
            if not item_name:
                continue

            raw_price = (row.get('Price') or '').strip()
            price_val = None
            if raw_price:
                try:
                    price_val = Decimal(raw_price)
                except InvalidOperation:
                    print(f"  Warning: could not parse price '{raw_price}' for '{item_name}', leaving blank (variable-priced).")

            item, created = ItemPrice.objects.get_or_create(
                item_name=item_name,
                variation_name='Regular',  # Defaulting to 'Regular' as Square often expects this
                defaults={
                    'ministry': (row.get('Categories') or '').strip(),
                    'price': price_val,
                }
            )
            if created:
                print(f"  Added item: {item.item_name}")
            else:
                print(f"  Already exists, skipped: {item.item_name}")


if __name__ == '__main__':
    import_pattern_rules()
    import_item_prices()
    print("\nDone! All items and patterns uploaded.")
