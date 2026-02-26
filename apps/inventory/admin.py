from django.contrib import admin
from django.utils.html import format_html

from .models import Product, Location, InventorySession, InventoryRecord, InboundRecord, InboundImage


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('barcode', 'name', 'display_name', 'created_at', 'updated_at')
    search_fields = ('barcode', 'name', 'display_name')
    ordering = ('name',)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('barcode', 'name', 'zone', 'created_at')
    search_fields = ('barcode', 'name')
    list_filter = ('zone',)


@admin.register(InventorySession)
class InventorySessionAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'started_at', 'ended_at', 'started_by')
    list_filter = ('status',)
    search_fields = ('name',)


@admin.register(InventoryRecord)
class InventoryRecordAdmin(admin.ModelAdmin):
    list_display = ('session', 'location', 'barcode', 'product_name', 'quantity', 'expiry_date', 'lot_number', 'worker', 'created_at')
    list_filter = ('session',)
    search_fields = ('barcode', 'product_name', 'lot_number', 'location__barcode')


class InboundImageInline(admin.TabularInline):
    """입고 이미지 인라인 (입고 기록 편집 시 이미지 관리)"""
    model = InboundImage
    extra = 1
    readonly_fields = ('image_preview', 'created_at')
    fields = ('image', 'image_preview', 'created_at')

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height:80px; border-radius:4px;" />', obj.image.url)
        return '-'
    image_preview.short_description = '미리보기'


@admin.register(InboundRecord)
class InboundRecordAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity', 'expiry_date', 'lot_number', 'status', 'image_count', 'registered_by', 'created_at', 'completed_by', 'completed_at')
    list_filter = ('status', 'created_at')
    search_fields = ('product__name', 'product__barcode', 'lot_number', 'memo')
    raw_id_fields = ('product', 'registered_by', 'completed_by')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [InboundImageInline]
    list_per_page = 30

    def image_count(self, obj):
        count = obj.images.count()
        return f'{count}장' if count else '-'
    image_count.short_description = '이미지'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product', 'registered_by', 'completed_by'
        ).prefetch_related('images')


@admin.register(InboundImage)
class InboundImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'inbound_record', 'image_preview', 'created_at')
    list_filter = ('created_at',)
    raw_id_fields = ('inbound_record',)
    readonly_fields = ('image_preview_large', 'created_at')

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height:40px; border-radius:4px;" />', obj.image.url)
        return '-'
    image_preview.short_description = '미리보기'

    def image_preview_large(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height:300px; border-radius:8px;" />', obj.image.url)
        return '-'
    image_preview_large.short_description = '이미지 미리보기'
