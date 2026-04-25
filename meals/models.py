import uuid
from django.db import models
from django.utils import timezone
from datetime import timedelta
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.hashers import make_password, check_password as django_check_password

# ─────────────────────────────────────────────
#  Branch
# ─────────────────────────────────────────────
class Branch(models.Model):
    BRANCH_TYPES = [
        ('dinners', '4pm Dinners'), ('coffee', 'Coffee Sundays'),
        ('jivers', 'Junior Jivers'), ('kids', 'Lighthouse Kids'), ('youth', 'Lighthouse Youth'),
    ]
    THEME_CHOICES = [
        ('green', 'Green (Dinners)'), ('amber', 'Amber (Coffee)'),
        ('coral', 'Coral (Junior Jivers)'), ('blue', 'Blue (Kids)'),
        ('purple', 'Purple (Youth)'), ('slate', 'Slate (Admin/Other)'),
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

# ─────────────────────────────────────────────
#  Product
# ─────────────────────────────────────────────
class Product(models.Model):
    branch        = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='products')
    name          = models.CharField(max_length=100)
    icon          = models.CharField(max_length=10, default='🎟️')
    credit_cost   = models.DecimalField(max_digits=6, decimal_places=2)
    topup_bundle  = models.PositiveIntegerField(default=10, help_text='Units per standard top-up bundle')
    topup_credits = models.PositiveIntegerField(default=10, help_text='Credits added per bundle purchase')
    price_aud     = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text='AUD price for one top-up bundle. Leave blank to disable online purchasing.'
    )
    is_active     = models.BooleanField(default=True)
    order         = models.PositiveIntegerField(default=0)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_active', 'order', '-created_at']

    def __str__(self):
        return f"{self.branch.name} — {self.name} ({self.credit_cost} cr)"

    @property
    def available_online(self):
        return self.price_aud is not None and self.price_aud > 0

# ─────────────────────────────────────────────
#  Family (The Unified Account)
# ─────────────────────────────────────────────
class Family(models.Model):
    display_name      = models.CharField(max_length=150)
    surname           = models.CharField(max_length=100, db_index=True)
    primary_contact   = models.CharField(max_length=100)
    pin_hash          = models.CharField(max_length=256)
    is_active         = models.BooleanField(default=True)
    
    # PIN recovery fields
    recovery_question = models.CharField(
        max_length=255, blank=True,
        help_text="e.g. \"What street did you grow up on?\""
    )
    recovery_answer   = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['surname', 'display_name']
        verbose_name_plural = 'Families'
        unique_together = [['surname', 'primary_contact']]

    def __str__(self):
        return self.display_name

    def set_recovery_answer(self, raw_answer):
        self.recovery_answer = make_password(raw_answer.strip().lower())

    def check_recovery_answer(self, raw_answer):
        return django_check_password(raw_answer.strip().lower(), self.recovery_answer)

# ─────────────────────────────────────────────
#  FamilyBalance (The Isolated Pockets)
# ─────────────────────────────────────────────
class FamilyBalance(models.Model):
    family  = models.ForeignKey(Family, on_delete=models.CASCADE, related_name='balances')
    branch  = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='balances')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        unique_together = [['family', 'branch']]
        ordering = ['branch__order', 'family__surname']

    def __str__(self):
        return f"{self.family.display_name} — {self.branch.name}: {self.balance} cr"

    def get_approx_quantities(self):
        results = []
        for product in self.branch.products.filter(is_active=True).order_by('credit_cost'):
            if product.credit_cost > 0:
                count = int(self.balance / product.credit_cost)
                if count > 0:
                    results.append(f"{count}× {product.name}")
        return results

# Auto-create pockets when a new Family is created
@receiver(post_save, sender=Family)
def create_family_balances(sender, instance, created, **kwargs):
    if created:
        FamilyBalance.objects.bulk_create(
            [FamilyBalance(family=instance, branch=b) for b in Branch.objects.filter(is_active=True)],
            ignore_conflicts=True,
        )

# Auto-create pockets for existing families if a new Branch is created
@receiver(post_save, sender=Branch)
def create_branch_balances(sender, instance, created, **kwargs):
    if created:
        FamilyBalance.objects.bulk_create(
            [FamilyBalance(family=f, branch=instance) for f in Family.objects.filter(is_active=True)],
            ignore_conflicts=True,
        )

# ─────────────────────────────────────────────
#  Child
# ─────────────────────────────────────────────
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
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

# ─────────────────────────────────────────────
#  Transaction & Audit Trail
# ─────────────────────────────────────────────
class Transaction(models.Model):
    REASON_CHOICES = [
        ('qr_redemption',    'QR Redemption'),
        ('manual_kiosk',     'Manual Kiosk Entry'),
        ('admin_adjustment', 'Admin Adjustment'),
        ('credit_top_up',    'Credit Top-Up'),
        ('online_topup',     'Online Top-Up (Square)'),
    ]
    PERFORMED_BY_CHOICES = [
        ('system_qr',       'System (QR)'),
        ('kiosk_volunteer', 'Kiosk Volunteer'),
        ('admin',           'Admin'),
        ('square_online',   'Square Online'),
    ]
    family       = models.ForeignKey(Family, on_delete=models.PROTECT, related_name='transactions')
    branch       = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='transactions', null=True, blank=True)
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
#  Square Payment Order
# ─────────────────────────────────────────────
class SquarePaymentOrder(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('completed', 'Completed'),
        ('failed',    'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    id                     = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family                 = models.ForeignKey(Family, on_delete=models.PROTECT, related_name='square_orders')
    branch                 = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='square_orders', null=True, blank=True)
    
    # Cart details replacing the single product FK
    cart_summary           = models.CharField(max_length=500, blank=True, help_text='e.g. "2× Adult Meal, 1× Kids Meal"')
    cart_data              = models.JSONField(default=list, blank=True, help_text='List of {name, quantity, unit_price_cents}')
    
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
        return f"{self.family} — {self.cart_summary} ${self.amount_aud} [{self.status}]"

# ─────────────────────────────────────────────
#  QR Code Nonce
# ─────────────────────────────────────────────
class QRCodeNonce(models.Model):
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family       = models.ForeignKey(Family, on_delete=models.PROTECT, related_name='qr_nonces')
    branch       = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='qr_nonces', null=True, blank=True)
    credit_units = models.DecimalField(max_digits=10, decimal_places=2)
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
        return f"QR for {self.family} — {self.credit_units} cr"

# ─────────────────────────────────────────────
#  Attendance
# ─────────────────────────────────────────────
class AttendanceRecord(models.Model):
    branch       = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='attendance_records')
    family       = models.ForeignKey(Family, on_delete=models.PROTECT, related_name='attendance_records')
    session_date = models.DateField(default=timezone.localdate, db_index=True)
    transaction  = models.OneToOneField(Transaction, on_delete=models.PROTECT, related_name='attendance_record', null=True, blank=True)
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