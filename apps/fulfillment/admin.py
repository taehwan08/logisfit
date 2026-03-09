"""
출고 관리 Django Admin 설정
"""
from django.contrib import admin
from .models import FulfillmentOrder, FulfillmentComment, PlatformColumnConfig


@admin.register(FulfillmentOrder)
class FulfillmentOrderAdmin(admin.ModelAdmin):
    """출고 주문 관리자 설정"""

    list_display = [
        'internal_code', 'client', 'brand', 'platform', 'product_name',
        'quantity', 'box_quantity', 'pallet_quantity', 'invoice_number',
        'status', 'created_at',
    ]
    list_filter = ['platform', 'status', 'client', 'brand']
    search_fields = ['product_name', 'invoice_number']
    ordering = ['-created_at']
    readonly_fields = [
        'internal_code',
        'confirmed_at', 'confirmed_by',
        'shipped_at', 'shipped_by',
        'synced_at', 'synced_by',
        'created_at', 'updated_at',
    ]
    raw_id_fields = ['client', 'brand', 'created_by']

    fieldsets = (
        ('기본 정보', {
            'fields': (
                'internal_code', 'client', 'brand', 'platform', 'status',
            ),
        }),
        ('고정 필드', {
            'fields': (
                'product_name', 'quantity', 'box_quantity',
                'pallet_quantity', 'invoice_number',
            ),
        }),
        ('커스텀 데이터 (JSON)', {
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
    search_fields = ['content']
    ordering = ['-created_at']
    raw_id_fields = ['order', 'author']

    @admin.display(description='내용')
    def content_short(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content


@admin.register(PlatformColumnConfig)
class PlatformColumnConfigAdmin(admin.ModelAdmin):
    """플랫폼 컬럼 설정 관리자"""

    list_display = ['platform', 'name', 'key', 'column_type', 'display_order', 'is_required', 'is_active']
    list_filter = ['platform', 'column_type', 'is_active']
    search_fields = ['name', 'key']
    ordering = ['platform', 'display_order']
    list_editable = ['display_order', 'is_required', 'is_active']
