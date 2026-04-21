"""
Management command: python manage.py seed_data
Creates sample families, pricing, and a superuser for testing.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from meals.models import Family, MealPricing
from meals.utils import hash_pin


SAMPLE_FAMILIES = [
    ("O'Shea", "O'Shea — Connan & Belinda",    "Connan O'Shea",  "0101"),
    ("Smith",  "Smith — James & Rachel",        "James Smith",    "1503"),
    ("Nguyen", "Nguyen — Minh & Linh",          "Minh Nguyen",    "2207"),
    ("Brown",  "Brown — David & Sarah",         "David Brown",    "0906"),
    ("Taylor", "Taylor — Michael & Kate",       "Michael Taylor", "1412"),
    ("Wilson", "Wilson — Andrew & Fiona",       "Andrew Wilson",  "3011"),
    ("Jones",  "Jones — Peter & Sue",           "Peter Jones",    "0804"),
    ("Lee",    "Lee — Daniel & Amy",            "Daniel Lee",     "1708"),
    ("Martin", "Martin — Chris & Joanne",       "Chris Martin",   "2502"),
    ("White",  "White — Robert & Lisa",         "Robert White",   "0710"),
]


class Command(BaseCommand):
    help = 'Seeds the database with sample families and pricing data.'

    def handle(self, *args, **options):
        # Pricing
        MealPricing.objects.get_or_create(meal_type='adult',  defaults={'unit_cost': 2, 'is_active': True})
        MealPricing.objects.get_or_create(meal_type='child',  defaults={'unit_cost': 1, 'is_active': True})
        self.stdout.write('✓ Pricing set: Adult=2 credits, Child=1 credit')

        # Families
        for surname, display_name, primary_contact, ddmm in SAMPLE_FAMILIES:
            family, created = Family.objects.get_or_create(
                surname=surname,
                primary_contact=primary_contact,
                defaults={
                    'display_name': display_name,
                    'pin_hash': hash_pin(ddmm),
                    'credit_units': 10,
                    'is_active': True,
                }
            )
            status = 'created' if created else 'exists'
            self.stdout.write(f'  {status}: {display_name} (PIN: {ddmm})')

        # Superuser
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@church.local', 'admin123')
            self.stdout.write('✓ Superuser created: admin / admin123')
        else:
            self.stdout.write('✓ Superuser already exists')

        self.stdout.write(self.style.SUCCESS('\nDatabase seeded successfully!'))
