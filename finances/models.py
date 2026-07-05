from django.db import models


class ImportBatch(models.Model):
    """One uploaded transaction report (a Square CSV/xlsx export, or a Stripe xlsx export)."""

    SOURCE_CHOICES = [
        ('square', 'Square'),
        ('stripe', 'Stripe'),
        ('stripe_ytd', 'Stripe YTD Unified'),
    ]

    source = models.CharField(max_length=10, choices=SOURCE_CHOICES)
    label = models.CharField(max_length=100, help_text="e.g. 'June 2026'")
    uploaded_file = models.FileField(upload_to='finances/uploads/%Y/%m/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    row_count = models.IntegerField(default=0)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.get_source_display()} — {self.label}"


class ItemPrice(models.Model):
    """
    Direct replacement for key.csv. One row per Square Item Library
    item/variation. Edit these in Django admin instead of hand-maintaining
    a CSV. Leave price blank for variable-priced items (revenue protection
    logic will trust the transaction's own gross sales figure instead).
    """
    item_name = models.CharField(max_length=200)
    variation_name = models.CharField(max_length=100, blank=True, default='Regular')
    ministry = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ('item_name', 'variation_name')
        ordering = ['item_name', 'variation_name']

    def __str__(self):
        return f"{self.item_name} ({self.variation_name}) → {self.ministry}"


class PatternRule(models.Model):
    """
    Regex classifier for transaction descriptions that DON'T come from the
    Square Item Library at all — subscription/credit-plan line items, the
    merch webstore, or anything else your other systems generate. Add a new
    rule here whenever a genuinely new transaction *shape* appears; you
    should not need one per SKU/colour/size/family.

    The pattern should contain a (?P<ministry>...) named group, UNLESS you
    set fixed_ministry, in which case every match is routed there regardless
    (useful for something like the merch store where you just want
    everything landing in one "Merch" bucket).
    """
    name = models.CharField(max_length=100, help_text="Label only, e.g. 'Meal credits'")
    pattern = models.CharField(max_length=500, help_text="Python regex, matched against the transaction description.")
    fixed_ministry = models.CharField(max_length=100, blank=True)
    priority = models.IntegerField(default=100, help_text="Lower numbers are tried first.")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['priority', 'name']

    def __str__(self):
        return self.name


class Transaction(models.Model):
    """A single classified, split, fee-reconciled line item, persisted so
    reports can be filtered/re-printed without re-parsing the source file."""

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name='transactions')
    source = models.CharField(max_length=10, choices=ImportBatch.SOURCE_CHOICES)
    date = models.DateField()
    ministry = models.CharField(max_length=100, default='Unknown')
    item = models.CharField(max_length=300, blank=True)
    qty = models.IntegerField(default=1)
    gross = models.DecimalField(max_digits=10, decimal_places=2)
    fees = models.DecimalField(max_digits=10, decimal_places=2)
    net = models.DecimalField(max_digits=10, decimal_places=2)
    external_id = models.CharField(max_length=200, blank=True)
    # Free-form extras from classifiers/importers: Family, Credits, Colour,
    # Size, Stripe customer reference, etc. Keeps the model stable even as
    # new transaction sources bring new metadata.
    extra = models.JSONField(blank=True, default=dict)

    class Meta:
        ordering = ['date', 'id']
        indexes = [
            models.Index(fields=['batch', 'ministry']),
            models.Index(fields=['date']),
        ]

    def __str__(self):
        return f"{self.date} {self.ministry} {self.item} ${self.gross}"
