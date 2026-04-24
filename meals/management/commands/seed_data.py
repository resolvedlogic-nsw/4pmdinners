"""
Management command: python manage.py seed_data
Creates sample branches, products, families, and a superuser for testing.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from meals.models import Branch, Product, Family
from meals.utils import hash_pin

SAMPLE_FAMILIES = [
    ("O'Shea", "O'Shea — Connan & Belinda",    "Connan",  "0101"),
    ("Smith",  "Smith — James & Rachel",        "James",   "1503"),
    ("Nguyen", "Nguyen — Minh & Linh",          "Minh",    "2207"),
    ("Brown",  "Brown — David & Sarah",         "David",   "0906"),
    ("Lee",    "Lee — Daniel & Amy",            "Daniel",  "1708"),
]

class Command(BaseCommand):
    help = 'Seeds the database with sample branches, products, and families.'

    def handle(self, *args, **options):
        # 1. Create a Branch
        branch, _ = Branch.objects.get_or_create(
            slug='dinners',
            defaults={
                'name': '4pm Dinners',
                'branch_type': 'dinners',
                'theme': 'green',
                'icon': '🍽️',
                'kiosk_pin_hash': hash_pin('1234'),
                'is_active': True
            }
        )
        self.stdout.write('✓ Branch created: 4pm Dinners (Kiosk PIN: 1234)')

        # 2. Create Products
        Product.objects.get_or_create(branch=branch, name='Adult Meal', defaults={'credit_cost': 2, 'icon': '🧑', 'topup_bundle': 10, 'topup_credits': 20, 'order': 1})
        Product.objects.get_or_create(branch=branch, name='Child Meal', defaults={'credit_cost': 1, 'icon': '🧒', 'topup_bundle': 10, 'topup_credits': 10, 'order': 2})
        self.stdout.write('✓ Products created: Adult (2cr), Child (1cr)')

        # 3. Create Families
        for surname, display_name, primary_contact, ddmm in SAMPLE_FAMILIES:
            Family.objects.get_or_create(
                branch=branch,
                surname=surname,
                primary_contact=primary_contact,
                defaults={
                    'display_name': display_name,
                    'pin_hash': hash_pin(ddmm),
                    'credit_units': 10,
                    'is_active': True,
                }
            )
            self.stdout.write(f'  Created: {display_name} (PIN: {ddmm})')

        # 4. Superuser
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@church.local', 'admin123')
            self.stdout.write('✓ Superuser created: admin / admin123')

        self.stdout.write(self.style.SUCCESS('\nDatabase seeded successfully!'))