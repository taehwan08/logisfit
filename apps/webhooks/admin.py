"""
웹훅 관리 어드민
"""
from django.contrib import admin

from .models import WebhookSubscriber, WebhookLog


class WebhookLogInline(admin.TabularInline):
    model = WebhookLog
    extra = 0
    readonly_fields = [
        'event', 'status_code', 'attempts', 'success',
        'error_message', 'created_at',
    ]
    fields = ['event', 'status_code', 'attempts', 'success', 'created_at']
    ordering = ['-created_at']


@admin.register(WebhookSubscriber)
class WebhookSubscriberAdmin(admin.ModelAdmin):
    list_display = ['name', 'url', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'url']
    inlines = [WebhookLogInline]


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = [
        'subscriber', 'event', 'status_code',
        'attempts', 'success', 'created_at',
    ]
    list_filter = ['event', 'success']
    search_fields = ['subscriber__name', 'event']
    readonly_fields = ['payload']
