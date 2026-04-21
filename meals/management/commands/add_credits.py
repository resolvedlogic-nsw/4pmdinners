"""
Management command: python manage.py add_credits <family_id> <amount>
Used by admins to top up a family's credit balance.
"""
from django.core.management.base import BaseCommand, CommandError
from meals.models import Family, Transaction


class Command(BaseCommand):
    help = 'Add credits to a family account.'

    def add_arguments(self, parser):
        parser.add_argument('family_id', type=int, help='Family ID')
        parser.add_argument('amount', type=int, help='Credits to add (positive integer)')
        parser.add_argument('--note', type=str, default='', help='Optional note')

    def handle(self, *args, **options):
        try:
            family = Family.objects.get(id=options['family_id'])
        except Family.DoesNotExist:
            raise CommandError(f"Family with id={options['family_id']} not found.")

        amount = options['amount']
        if amount <= 0:
            raise CommandError('Amount must be a positive integer.')

        family.credit_units += amount
        family.save(update_fields=['credit_units'])

        Transaction.objects.create(
            family=family,
            credit_delta=amount,
            reason='credit_top_up',
            performed_by='admin',
            notes=options['note'],
        )

        self.stdout.write(self.style.SUCCESS(
            f'✓ Added {amount} credits to {family.display_name}. New balance: {family.credit_units}.'
        ))
