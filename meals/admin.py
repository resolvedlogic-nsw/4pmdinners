from django.contrib import admin
from django.utils.html import format_html
from .models import Branch, Product, Family, FamilyBalance, Child, Transaction, QRCodeNonce, AttendanceRecord, AttendanceChild
from django.http import HttpResponse
import csv, datetime
# ─── Branch ───────────────────────────────────────────────────────────────────

@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display  = ['name', 'slug', 'branch_type', 'theme', 'icon', 'is_active', 'is_children_programme', 'is_no_fee_programme', 'order']
    list_editable = ['order', 'is_active']
    prepopulated_fields = {'slug': ('name',)}


# ─── Product ──────────────────────────────────────────────────────────────────

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display  = ['name', 'branch', 'credit_cost', 'topup_bundle', 'topup_credits', 'is_active', 'order']
    list_filter   = ['branch', 'is_active']
    list_editable = ['order', 'is_active']


# ─── Family ───────────────────────────────────────────────────────────────────

class FamilyBalanceInline(admin.TabularInline):
    model = FamilyBalance
    extra = 0
    readonly_fields = ['branch', 'balance']
    can_delete = False

class ChildInline(admin.TabularInline):
    model = Child
    extra = 0
    fields = ['first_name', 'last_name', 'date_of_birth', 'is_active']


# ─── Transaction ──────────────────────────────────────────────────────────────

@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    # Removed 'branch' and 'credit_units' from list_display
    list_display = ['display_name', 'surname', 'primary_contact', 'is_active']
    # Removed 'branch' from list_filter
    list_filter = ['is_active']
    search_fields = ['display_name', 'surname', 'primary_contact']
    # Removed 'branch' from ordering
    ordering = ['surname']
    inlines = [FamilyBalanceInline, ChildInline]

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    # Changed filter from family__branch to just branch
    list_display = ['timestamp', 'family', 'branch', 'credit_delta', 'reason', 'performed_by']
    list_filter = ['branch', 'reason', 'performed_by']
    search_fields = ['family__display_name', 'family__surname']
    
# ─── QR Nonce ─────────────────────────────────────────────────────────────────

@admin.register(QRCodeNonce)
class QRCodeNonceAdmin(admin.ModelAdmin):
    list_display = ['family', 'branch', 'credit_units', 'created_at', 'used']
    # Changed filter from family__branch to just branch
    list_filter = ['used', 'branch']


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
