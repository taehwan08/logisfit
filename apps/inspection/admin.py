"""
검수 시스템 관리자 설정
"""
from django.contrib import admin
from .models import Order, OrderProduct, InspectionLog


class OrderProductInline(admin.TabularInline):
    model = OrderProduct
    extra = 0
    readonly_fields = ('scanned_quantity',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('tracking_number', 'seller', 'receiver_name', 'status', 'uploaded_at', 'completed_at')
    list_filter = ('status', 'seller', 'uploaded_at')
    search_fields = ('tracking_number', 'receiver_name', 'seller')
    readonly_fields = ('uploaded_at', 'completed_at')
    inlines = [OrderProductInline]


@admin.register(OrderProduct)
class OrderProductAdmin(admin.ModelAdmin):
    list_display = ('order', 'barcode', 'product_name', 'quantity', 'scanned_quantity')
    search_fields = ('barcode', 'product_name', 'order__tracking_number')


@admin.register(InspectionLog)
class InspectionLogAdmin(admin.ModelAdmin):
    list_display = ('tracking_number', 'barcode', 'scan_type', 'alert_code', 'worker', 'created_at')
    list_filter = ('scan_type', 'alert_code', 'created_at')
    search_fields = ('tracking_number', 'barcode', 'worker')
    readonly_fields = ('created_at',)
