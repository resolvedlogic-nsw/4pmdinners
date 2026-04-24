import uuid
from django.db import models
from django.utils import timezone
from datetime import timedelta


# ─────────────────────────────────────────────
#  Branch
# ─────────────────────────────────────────────

class Branch(models.Model):
    BRANCH_TYPES = [
        ('dinners',  '4pm Dinners'),
        ('coffee',   'Coffee Sundays'),
        ('jivers',   'Junior Jivers'),
        ('kids',     'Lighthouse Kids'),
        ('youth',    'Lighthouse Youth'),
    ]
    THEME_CHOICES = [
        ('green',   'Green (Dinners)'),
        ('amber',   'Amber (Coffee)'),
        ('coral',   'Coral (Junior Jivers)'),
        ('blue',    'Blue (Kids)'),
        ('purple',  'Purple (Youth)'),
        ('slate',   'Slate (Admin/Other)'),
    ]

    name           = models.CharField(max_length=100)
    slug           = models.SlugField(unique=True)
    branch_type    = models.CharField(max_length=20, choices=BRANCH_TYPES)
    theme          = models.CharField(max_length=20, choices=THEME_CHOICES, default='green')
    icon           = models.CharField(max_length=10, default='🍽️', help_text='Emoji icon for this branch')
    description    = models.CharField(max_length=255, blank=True)
    kiosk_pin_hash = models.CharField(max_length=256, help_text='Hashed kiosk PIN for this branch')
    is_active      = models.BooleanField(default=True)
    is_children_programme = models.BooleanField(
        default=False,
        help_text='If true, check-in uses child selection + attendance records instead of adult/child counters'
    )
    order          = models.PositiveIntegerField(default=0, help_text='Display order on home page')

    class Meta:
        ordering = ['order', 'name']
        verbose_name_plural = 'Branches'

    def __str__(self):
        return self.name


# ─────────────────────────────────────────────
#  Product (replaces hardcoded adult/child pricing)
# ─────────────────────────────────────────────

class Product(models.Model):
    branch          = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='products')
    name            = models.CharField(max_length=100, help_text='e.g. "Adult Meal", "Coffee", "Weekly Session"')
    icon            = models.CharField(max_length=10, default='🎟️')
    credit_cost     = models.DecimalField(max_digits=6, decimal_places=2, help_text='Credits deducted per unit (can be 0.5)')
    topup_bundle    = models.PositiveIntegerField(default=10, help_text='How many units per standard top-up bundle')
    topup_credits   = models.PositiveIntegerField(default=10, help_text='Credits added per top-up bundle purchase')
    is_active       = models.BooleanField(default=True)
    order           = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return f"{self.branch.name} — {self.name} ({self.credit_cost} cr)"


# ─────────────────────────────────────────────
#  Family
# ─────────────────────────────────────────────

class Family(models.Model):
    branch          = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='families')
    display_name    = models.CharField(max_length=150)
    surname         = models.CharField(max_length=100, db_index=True)
    primary_contact = models.CharField(max_length=100)
    pin_hash        = models.CharField(max_length=256)
    credit_units    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active       = models.BooleanField(default=True)

    class Meta:
        ordering = ['surname', 'display_name']
        verbose_name_plural = 'Families'
        unique_together = [['branch', 'surname', 'primary_contact']]

    def __str__(self):
        return f"{self.display_name} ({self.branch.name})"

    def can_afford(self, cost):
        return self.credit_units >= cost

    def max_of_product(self, product):
        if product.credit_cost == 0:
            return 99
        return int(self.credit_units // product.credit_cost)


# ─────────────────────────────────────────────
#  Child  (children's programmes only)
# ─────────────────────────────────────────────

class Child(models.Model):
    family      = models.ForeignKey(Family, on_delete=models.CASCADE, related_name='children')
    first_name  = models.CharField(max_length=100)
    last_name   = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    is_active   = models.BooleanField(default=True)

    class Meta:
        ordering = ['first_name', 'last_name']
        verbose_name_plural = 'Children'

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


# ─────────────────────────────────────────────
#  Transaction
# ─────────────────────────────────────────────

class Transaction(models.Model):
    REASON_CHOICES = [
        ('qr_redemption',    'QR Redemption'),
        ('manual_kiosk',     'Manual Kiosk Entry'),
        ('admin_adjustment', 'Admin Adjustment'),
        ('credit_top_up',    'Credit Top-Up'),
    ]
    PERFORMED_BY_CHOICES = [
        ('system_qr',      'System (QR)'),
        ('kiosk_volunteer','Kiosk Volunteer'),
        ('admin',          'Admin'),
    ]

    family       = models.ForeignKey(Family, on_delete=models.PROTECT, related_name='transactions')
    credit_delta = models.DecimalField(max_digits=10, decimal_places=2)
    reason       = models.CharField(max_length=30, choices=REASON_CHOICES)
    performed_by = models.CharField(max_length=20, choices=PERFORMED_BY_CHOICES)
    notes        = models.CharField(max_length=255, blank=True)
    timestamp    = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        sign = '+' if self.credit_delta >= 0 else ''
        return f"{self.family} {sign}{self.credit_delta} ({self.reason})"


# ─────────────────────────────────────────────
#  QR Code Nonce
# ─────────────────────────────────────────────

class QRCodeNonce(models.Model):
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family       = models.ForeignKey(Family, on_delete=models.PROTECT, related_name='qr_nonces')
    credit_units = models.DecimalField(max_digits=10, decimal_places=2)
    # For dinners/coffee — simple counts
    adult_count  = models.PositiveIntegerField(default=0)
    child_count  = models.PositiveIntegerField(default=0)
    # For children's programmes — JSON list of Child PKs
    child_ids    = models.JSONField(default=list, blank=True)
    created_at   = models.DateTimeField(default=timezone.now)
    expires_at   = models.DateTimeField()
    used         = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = self.created_at + timedelta(minutes=30)
        super().save(*args, **kwargs)

    def is_valid(self):
        return not self.used and timezone.now() < self.expires_at

    def __str__(self):
        return f"QR for {self.family} — {self.credit_units} cr ({'used' if self.used else 'valid'})"


# ─────────────────────────────────────────────
#  Attendance  (children's programmes only)
# ─────────────────────────────────────────────

class AttendanceRecord(models.Model):
    branch      = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='attendance_records')
    family      = models.ForeignKey(Family, on_delete=models.PROTECT, related_name='attendance_records')
    session_date = models.DateField(default=timezone.localdate, db_index=True)
    transaction  = models.OneToOneField(Transaction, on_delete=models.PROTECT, related_name='attendance_record', null=True, blank=True)
    timestamp    = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-session_date', 'family__surname']

    def __str__(self):
        return f"{self.family} @ {self.branch} on {self.session_date}"


class AttendanceChild(models.Model):
    """Each child present at a session."""
    record  = models.ForeignKey(AttendanceRecord, on_delete=models.CASCADE, related_name='children_present')
    child   = models.ForeignKey(Child, on_delete=models.PROTECT)

    class Meta:
        unique_together = [['record', 'child']]

    def __str__(self):
        return f"{self.child} at {self.record}"
