"""
거래처 Admin 모듈

Django Admin에서 거래처, 단가 계약을 관리합니다.
"""
from django.contrib import admin
from django.utils.html import format_html

from .models import Client, Brand, PriceContract


class BrandInline(admin.TabularInline):
    """브랜드 인라인 (거래처 Admin에서 사용)"""
    model = Brand
    extra = 1
    readonly_fields = ('created_at', 'created_by')
    fields = ('name', 'code', 'is_active', 'memo', 'created_by', 'created_at')


class PriceContractInline(admin.TabularInline):
    """단가 계약 인라인 (거래처 Admin에서 사용)"""
    model = PriceContract
    extra = 0
    readonly_fields = ('created_at', 'created_by')
    fields = ('work_type', 'sub_category', 'item_name', 'unit_price', 'unit', 'quantity', 'remarks', 'valid_from', 'valid_to', 'memo', 'created_by', 'created_at')


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    """거래처 Admin"""
    list_display = (
        'company_name', 'business_number', 'contact_person',
        'contact_phone', 'is_active_display', 'contract_status', 'created_at',
    )
    list_filter = ('is_active', 'created_at', 'contract_start_date')
    search_fields = ('company_name', 'business_number', 'contact_person', 'contact_email')
    readonly_fields = ('created_at', 'updated_at', 'created_by')
    inlines = [BrandInline, PriceContractInline]

    fieldsets = (
        ('기본 정보', {
            'fields': ('company_name', 'business_number', 'is_active'),
        }),
        ('담당자 정보', {
            'fields': ('contact_person', 'contact_phone', 'contact_email'),
        }),
        ('계약 정보', {
            'fields': ('contract_start_date', 'contract_end_date'),
        }),
        ('청구서 정보', {
            'fields': ('invoice_email', 'invoice_day'),
        }),
        ('주소', {
            'classes': ('collapse',),
            'fields': ('address', 'address_detail'),
        }),
        ('기타', {
            'fields': ('memo',),
        }),
        ('시스템 정보', {
            'classes': ('collapse',),
            'fields': ('created_by', 'created_at', 'updated_at'),
        }),
    )

    @admin.display(description='상태', ordering='is_active')
    def is_active_display(self, obj):
        if obj.is_active:
            return format_html('<span style="color: green;">● 활성</span>')
        return format_html('<span style="color: red;">● 비활성</span>')

    @admin.display(description='계약 상태')
    def contract_status(self, obj):
        if obj.is_contract_active:
            return format_html('<span style="color: green;">유효</span>')
        return format_html('<span style="color: orange;">만료</span>')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    """브랜드 Admin"""
    list_display = ('name', 'client', 'code', 'is_active', 'created_at')
    list_filter = ('is_active', 'client')
    search_fields = ('name', 'code', 'client__company_name')
    autocomplete_fields = ('client',)
    readonly_fields = ('created_at', 'updated_at', 'created_by')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PriceContract)
class PriceContractAdmin(admin.ModelAdmin):
    """단가 계약 Admin"""
    list_display = (
        'client', 'work_type', 'sub_category', 'item_name',
        'unit_price', 'unit', 'quantity',
        'valid_from', 'valid_to', 'is_active_display',
    )
    list_filter = ('work_type', 'valid_from')
    search_fields = ('client__company_name',)
    autocomplete_fields = ('client',)
    readonly_fields = ('created_at', 'created_by')

    @admin.display(description='상태')
    def is_active_display(self, obj):
        if obj.is_active:
            return format_html('<span style="color: green;">● 유효</span>')
        return format_html('<span style="color: gray;">● 만료</span>')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
