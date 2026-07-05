from django.contrib import admin
from .models import ImportBatch, ItemPrice, PatternRule, Transaction


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ('label', 'source', 'uploaded_at', 'row_count')
    list_filter = ('source',)
    ordering = ('-uploaded_at',)


@admin.register(ItemPrice)
class ItemPriceAdmin(admin.ModelAdmin):
    list_display = ('item_name', 'variation_name', 'ministry', 'price')
    list_filter = ('ministry',)
    search_fields = ('item_name', 'ministry')
    ordering = ('item_name',)


@admin.register(PatternRule)
class PatternRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'pattern', 'fixed_ministry', 'priority', 'active')
    list_editable = ('priority', 'active')
    ordering = ('priority',)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('date', 'batch', 'ministry', 'item', 'gross', 'fees', 'net')
    list_filter = ('batch', 'ministry', 'source')
    search_fields = ('item', 'external_id')
    ordering = ('-date',)
