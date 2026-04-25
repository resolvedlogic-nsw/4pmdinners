import uuid
from django.db import models
from django.utils import timezone
from datetime import timedelta


class Branch(models.Model):
    BRANCH_TYPES = [
        ('dinners', '4pm Dinners'), ('coffee', 'Coffee Sundays'),
        ('jivers', 'Junior Jivers'), ('kids', 'Lighthouse Kids'), ('youth', 'Lighthouse Youth'),
    ]
    THEME_CHOICES = [
        ('green', 'Green (Dinners)'), ('amber', 'Amber (Coffee)'), ('coral', 'Coral (Junior Jivers)'),
        ('blue', 'Blue (Kids)'), ('purple', 'Purple (Youth)'), ('slate', 'Slate (Admin/Other)'),
    ]
    name                  = models.CharField(max_length=100)
    slug                  = models.SlugField(unique=True)
    branch_type           = models.CharField(max_length=20, choices=BRANCH_TYPES)
    theme                 = models.CharField(max_length=20, choices=THEME_CHOICES, default='green')
    icon                  = models.CharField(max_length=10, default='🍽️')
    description           = models.CharField(max_length=255, blank=True)
    kiosk_pin_hash        = models.CharField(max_length=256)
    is_active             = models.BooleanField(default=True)
    is_children_programme = models.BooleanField(default=False)
    order                 = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']
        verbose_name_plural = 'Branches'

    def __str__(self):
        return self.name


class Product(models.Model):
    branch        = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='products')
    name          = models.CharField(max_length=100)
    icon          = models.CharField(max_length=10, default='🎟️')
    credit_cost   = models.DecimalField(max_digits=6, decimal_places=2)
    topup_bundle  = models.PositiveIntegerField(default=10)
    topup_credits = models.PositiveIntegerField(default=10)
    price_aud     = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text='AUD price for one top-up bundle. Leave blank to disable online purchasing for this product.'
    )
    is_active     = models.BooleanField(default=True)
    order         = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return f"{self.branch.name} — {self.name} ({self.credit_cost} cr)"

    @property
    def available_online(self):
        return self.price_aud is not None and self.price_aud > 0


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


class Child(models.Model):
    family        = models.ForeignKey(Family, on_delete=models.CASCADE, related_name='children')
    first_name    = models.CharField(max_length=100)
    last_name     = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    is_active     = models.BooleanField(default=True)

    class Meta:
        ordering = ['first_name', 'last_name']
        verbose_name_plural = 'Children'

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


class Transaction(models.Model):
    REASON_CHOICES = [
        ('qr_redemption',    'QR Redemption'),
        ('manual_kiosk',     'Manual Kiosk Entry'),
        ('admin_adjustment', 'Admin Adjustment'),
        ('credit_top_up',    'Credit Top-Up'),
        ('online_topup',     'Online Top-Up (Square)'),
    ]
    PERFORMED_BY_CHOICES = [
        ('system_qr',      'System (QR)'),
        ('kiosk_volunteer','Kiosk Volunteer'),
        ('admin',          'Admin'),
        ('square_online',  'Square Online'),
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


class SquarePaymentOrder(models.Model):
    """Tracks each online top-up attempt through Square."""
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('completed', 'Completed'),
        ('failed',    'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    id                     = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family                 = models.ForeignKey(Family, on_delete=models.PROTECT, related_name='square_orders')
    
    # --- CART UPDATES ---
    product                = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    quantity               = models.PositiveIntegerField(default=1)
    cart_summary           = models.CharField(max_length=255, blank=True)
    cart_data              = models.JSONField(default=list, blank=True)
    # --------------------

    credits_to_add         = models.DecimalField(max_digits=10, decimal_places=2)
    amount_aud             = models.DecimalField(max_digits=8, decimal_places=2)
    square_order_id        = models.CharField(max_length=200, blank=True)
    square_payment_link_id = models.CharField(max_length=200, blank=True)
    square_payment_id      = models.CharField(max_length=200, blank=True)
    status                 = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at             = models.DateTimeField(default=timezone.now)
    completed_at           = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        # Update the string representation to use the new cart summary
        return f"{self.family} — {self.cart_summary} ${self.amount_aud} [{self.status}]"

class QRCodeNonce(models.Model):
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family       = models.ForeignKey(Family, on_delete=models.PROTECT, related_name='qr_nonces')
    credit_units = models.DecimalField(max_digits=10, decimal_places=2)
    adult_count  = models.PositiveIntegerField(default=0)
    child_count  = models.PositiveIntegerField(default=0)
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


class AttendanceRecord(models.Model):
    branch       = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='attendance_records')
    family       = models.ForeignKey(Family, on_delete=models.PROTECT, related_name='attendance_records')
    session_date = models.DateField(default=timezone.localdate, db_index=True)
    transaction  = models.OneToOneField(Transaction, on_delete=models.PROTECT,
                                        related_name='attendance_record', null=True, blank=True)
    timestamp    = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-session_date', 'family__surname']

    def __str__(self):
        return f"{self.family} @ {self.branch} on {self.session_date}"


class AttendanceChild(models.Model):
    record = models.ForeignKey(AttendanceRecord, on_delete=models.CASCADE, related_name='children_present')
    child  = models.ForeignKey(Child, on_delete=models.PROTECT)

    class Meta:
        unique_together = [['record', 'child']]

    def __str__(self):
        return f"{self.child} at {self.record}"