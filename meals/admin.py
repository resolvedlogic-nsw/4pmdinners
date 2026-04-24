from django.contrib import admin
from django.utils.html import format_html
from django.http import HttpResponse
import csv, datetime
from .models import Branch, Product, Family, Child, Transaction, QRCodeNonce, AttendanceRecord, AttendanceChild


# ─── Branch ───────────────────────────────────────────────────────────────────

@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display  = ['name', 'slug', 'branch_type', 'theme', 'icon', 'is_active', 'is_children_programme', 'order']
    list_editable = ['order', 'is_active']
    prepopulated_fields = {'slug': ('name',)}


# ─── Product ──────────────────────────────────────────────────────────────────

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display  = ['name', 'branch', 'credit_cost', 'topup_bundle', 'topup_credits', 'is_active', 'order']
    list_filter   = ['branch', 'is_active']
    list_editable = ['order', 'is_active']


# ─── Family ───────────────────────────────────────────────────────────────────

class ChildInline(admin.TabularInline):
    model  = Child
    extra  = 1
    fields = ['first_name', 'last_name', 'date_of_birth', 'is_active']


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display   = ['display_name', 'surname', 'branch', 'primary_contact', 'credit_units', 'is_active']
    list_filter    = ['branch', 'is_active']
    search_fields  = ['display_name', 'surname', 'primary_contact']
    ordering       = ['branch', 'surname']
    readonly_fields = ['pin_hash']
    inlines        = [ChildInline]

    def get_fields(self, request, obj=None):
        fields = ['branch', 'display_name', 'surname', 'primary_contact', 'credit_units', 'is_active']
        if obj:
            fields.append('pin_hash')
        return fields


# ─── Transaction ──────────────────────────────────────────────────────────────

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display   = ['timestamp', 'family', 'branch_name', 'credit_delta_display', 'reason', 'performed_by']
    list_filter    = ['family__branch', 'reason', 'performed_by']
    search_fields  = ['family__display_name', 'family__surname']
    readonly_fields = ['family', 'credit_delta', 'reason', 'performed_by', 'timestamp']

    def branch_name(self, obj):
        return obj.family.branch.name
    branch_name.short_description = 'Branch'

    def credit_delta_display(self, obj):
        if obj.credit_delta >= 0:
            return format_html('<span style="color:green">+{}</span>', obj.credit_delta)
        return format_html('<span style="color:red">{}</span>', obj.credit_delta)
    credit_delta_display.short_description = 'Credits'

    def has_add_permission(self, request):
        return False


# ─── QR Nonce ─────────────────────────────────────────────────────────────────

@admin.register(QRCodeNonce)
class QRCodeNonceAdmin(admin.ModelAdmin):
    list_display  = ['family', 'credit_units', 'created_at', 'expires_at', 'used']
    list_filter   = ['used', 'family__branch']
    readonly_fields = ['id', 'family', 'credit_units', 'created_at', 'expires_at', 'used']


# ─── Attendance ───────────────────────────────────────────────────────────────

class AttendanceChildInline(admin.TabularInline):
    model  = AttendanceChild
    extra  = 0
    readonly_fields = ['child']
    can_delete = False


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display   = ['session_date', 'branch', 'family', 'child_count', 'timestamp']
    list_filter    = ['branch', 'session_date']
    search_fields  = ['family__display_name', 'family__surname']
    readonly_fields = ['branch', 'family', 'session_date', 'transaction', 'timestamp']
    inlines        = [AttendanceChildInline]
    actions        = ['export_csv']

    def child_count(self, obj):
        return obj.children_present.count()
    child_count.short_description = '# Children'

    def export_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="attendance.csv"'
        writer = csv.writer(response)
        writer.writerow(['Date', 'Branch', 'Family', 'Child', 'Time'])
        for record in queryset.prefetch_related('children_present__child'):
            for cp in record.children_present.all():
                writer.writerow([
                    record.session_date,
                    record.branch.name,
                    record.family.display_name,
                    cp.child.full_name,
                    record.timestamp.strftime('%H:%M'),
                ])
        return response
    export_csv.short_description = 'Export selected as CSV'
