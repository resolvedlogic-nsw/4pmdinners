from django.contrib import admin
from django.utils.html import format_html
from .models import Family, MealPricing, Transaction, QRCodeNonce


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'surname', 'primary_contact', 'credit_units', 'is_active']
    list_filter = ['is_active']
    search_fields = ['display_name', 'surname', 'primary_contact']
    ordering = ['surname']
    readonly_fields = ['pin_hash']

    def get_fields(self, request, obj=None):
        fields = ['display_name', 'surname', 'primary_contact', 'credit_units', 'is_active']
        if obj:
            fields.append('pin_hash')
        return fields


@admin.register(MealPricing)
class MealPricingAdmin(admin.ModelAdmin):
    list_display = ['meal_type', 'unit_cost', 'active_from', 'is_active']
    list_filter = ['meal_type', 'is_active']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'family', 'credit_delta_display', 'reason', 'performed_by']
    list_filter = ['reason', 'performed_by']
    search_fields = ['family__display_name', 'family__surname']
    readonly_fields = ['family', 'credit_delta', 'reason', 'performed_by', 'timestamp']

    def credit_delta_display(self, obj):
        if obj.credit_delta >= 0:
            return format_html('<span style="color:green">+{}</span>', obj.credit_delta)
        return format_html('<span style="color:red">{}</span>', obj.credit_delta)
    credit_delta_display.short_description = 'Credits'

    def has_add_permission(self, request):
        return False


@admin.register(QRCodeNonce)
class QRCodeNonceAdmin(admin.ModelAdmin):
    list_display = ['family', 'credit_units', 'created_at', 'expires_at', 'used']
    list_filter = ['used']
    readonly_fields = ['id', 'family', 'credit_units', 'created_at', 'expires_at', 'used']
