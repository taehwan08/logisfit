"""
출고 관리 Django Admin 설정
"""
from django.contrib import admin
from .models import FulfillmentOrder, FulfillmentComment


@admin.register(FulfillmentOrder)
class FulfillmentOrderAdmin(admin.ModelAdmin):
    """출고 주문 관리자 설정"""

    list_display = [
        'order_number', 'client', 'platform', 'product_name',
        'order_quantity', 'status', 'order_date', 'created_at',
    ]
    list_filter = ['platform', 'status', 'client', 'order_date']
    search_fields = ['order_number', 'product_name', 'barcode']
    ordering = ['-order_date', '-created_at']
    readonly_fields = [
        'confirmed_at', 'confirmed_by',
        'shipped_at', 'shipped_by',
        'synced_at', 'synced_by',
        'created_at', 'updated_at',
    ]
    raw_id_fields = ['client', 'created_by']

    fieldsets = (
        ('기본 정보', {
            'fields': (
                'client', 'platform', 'order_number', 'order_date', 'status',
            ),
        }),
        ('상품 정보', {
            'fields': (
                'product_name', 'barcode', 'order_quantity',
                'box_quantity', 'expiry_date',
            ),
        }),
        ('기타 정보', {
            'fields': (
                'manager', 'receiving_date', 'address', 'memo',
            ),
        }),
        ('플랫폼별 데이터', {
            'fields': ('platform_data',),
            'classes': ('collapse',),
        }),
        ('상태 추적', {
            'fields': (
                'confirmed_at', 'confirmed_by',
                'shipped_at', 'shipped_by',
                'synced_at', 'synced_by',
            ),
        }),
        ('시스템 정보', {
            'fields': ('created_by', 'created_at', 'updated_at'),
        }),
    )


class FulfillmentCommentInline(admin.TabularInline):
    """출고 주문 댓글 인라인"""
    model = FulfillmentComment
    extra = 0
    readonly_fields = ['author', 'created_at']
    fields = ['author', 'content', 'is_system', 'created_at']


# FulfillmentOrderAdmin에 인라인 추가
FulfillmentOrderAdmin.inlines = [FulfillmentCommentInline]


@admin.register(FulfillmentComment)
class FulfillmentCommentAdmin(admin.ModelAdmin):
    """출고 주문 댓글 관리자 설정"""

    list_display = ['order', 'author', 'content_short', 'is_system', 'created_at']
    list_filter = ['is_system', 'created_at']
    search_fields = ['content', 'order__order_number']
    ordering = ['-created_at']
    raw_id_fields = ['order', 'author']

    @admin.display(description='내용')
    def content_short(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
