import uuid
from django.db import models
from django.utils import timezone
from datetime import timedelta


class Family(models.Model):
    display_name = models.CharField(max_length=150)
    surname = models.CharField(max_length=100, db_index=True)
    primary_contact = models.CharField(max_length=100)
    pin_hash = models.CharField(max_length=256)
    credit_units = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['surname', 'display_name']
        verbose_name_plural = 'Families'

    def __str__(self):
        return self.display_name

    def can_afford(self, adult_count, child_count):
        pricing = MealPricing.get_active_pricing()
        total_cost = (
            adult_count * pricing['adult'] +
            child_count * pricing['child']
        )
        return self.credit_units >= total_cost

    def max_meals_of_type(self, meal_type):
        pricing = MealPricing.get_active_pricing()
        unit_cost = pricing.get(meal_type, 1)
        if unit_cost == 0:
            return 99
        return self.credit_units // unit_cost


class MealPricing(models.Model):
    MEAL_TYPES = [('adult', 'Adult'), ('child', 'Child')]

    meal_type = models.CharField(max_length=10, choices=MEAL_TYPES)
    unit_cost = models.PositiveIntegerField()
    active_from = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-active_from']
        verbose_name_plural = 'Meal Pricings'

    def __str__(self):
        return f"{self.get_meal_type_display()} — {self.unit_cost} credits"

    @classmethod
    def get_active_pricing(cls):
        result = {}
        for meal_type, _ in cls.MEAL_TYPES:
            pricing = cls.objects.filter(
                meal_type=meal_type, is_active=True
            ).order_by('-active_from').first()
            result[meal_type] = pricing.unit_cost if pricing else 1
        return result


class Transaction(models.Model):
    REASON_CHOICES = [
        ('qr_redemption', 'QR Redemption'),
        ('manual_kiosk_entry', 'Manual Kiosk Entry'),
        ('admin_adjustment', 'Admin Adjustment'),
        ('credit_top_up', 'Credit Top-Up'),
    ]
    PERFORMED_BY_CHOICES = [
        ('system_qr', 'System (QR)'),
        ('kiosk_volunteer', 'Kiosk Volunteer'),
        ('admin', 'Admin'),
    ]

    family = models.ForeignKey(Family, on_delete=models.PROTECT, related_name='transactions')
    credit_delta = models.IntegerField()
    reason = models.CharField(max_length=30, choices=REASON_CHOICES)
    performed_by = models.CharField(max_length=20, choices=PERFORMED_BY_CHOICES)
    notes = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        sign = '+' if self.credit_delta >= 0 else ''
        return f"{self.family} {sign}{self.credit_delta} ({self.reason})"


class QRCodeNonce(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family = models.ForeignKey(Family, on_delete=models.PROTECT, related_name='qr_nonces')
    credit_units = models.PositiveIntegerField()
    adult_count = models.PositiveIntegerField(default=0)
    child_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = self.created_at + timedelta(minutes=30)
        super().save(*args, **kwargs)

    def is_valid(self):
        return not self.used and timezone.now() < self.expires_at

    def __str__(self):
        return f"QR for {self.family} — {self.credit_units} units ({'used' if self.used else 'valid'})"
