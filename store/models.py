# store/models.py
from django.db import models


class Order(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending payment'),
        (STATUS_PAID, 'Paid'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    name = models.CharField(max_length=200)
    email = models.EmailField()
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    square_payment_link_id = models.CharField(max_length=100, blank=True)
    square_order_id = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.pk} – {self.name} ({self.get_status_display()})"

    @property
    def total(self):
        return sum(item.subtotal for item in self.items.all())

    @property
    def item_count(self):
        return sum(item.qty for item in self.items.all())


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product_slug = models.CharField(max_length=100)
    product_name = models.CharField(max_length=200)
    colour = models.CharField(max_length=50)
    size = models.CharField(max_length=20)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    qty = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.qty}x {self.product_name} ({self.colour}, {self.size})"

    @property
    def subtotal(self):
        return self.price * self.qty
