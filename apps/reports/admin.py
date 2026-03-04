"""
리포트 어드민
"""
from django.contrib import admin

from .models import ReportFile


@admin.register(ReportFile)
class ReportFileAdmin(admin.ModelAdmin):
    list_display = ('id', 'report_type', 'status', 'row_count', 'created_by', 'created_at', 'completed_at')
    list_filter = ('report_type', 'status')
    readonly_fields = ('params', 'file', 'error_message', 'created_at', 'completed_at')
