"""
리포트 모델
"""
from django.db import models


class ReportFile(models.Model):
    """비동기 리포트 파일"""

    STATUS_CHOICES = [
        ('PENDING', '대기'),
        ('PROCESSING', '생성중'),
        ('COMPLETED', '완료'),
        ('FAILED', '실패'),
    ]

    REPORT_TYPE_CHOICES = [
        ('INVENTORY_LEDGER', '재고원장'),
        ('SHIPMENT_SUMMARY', '출고요약'),
        ('WORKER_PRODUCTIVITY', '작업자생산성'),
        ('SAFETY_STOCK_ALERT', '안전재고알림'),
    ]

    report_type = models.CharField(
        '리포트 유형', max_length=30, choices=REPORT_TYPE_CHOICES,
    )
    status = models.CharField(
        '상태', max_length=20, choices=STATUS_CHOICES, default='PENDING',
    )
    params = models.JSONField('조회 조건', default=dict)
    file = models.FileField(
        '파일', upload_to='reports/%Y/%m/', blank=True, default='',
    )
    file_name = models.CharField('파일명', max_length=200, blank=True, default='')
    row_count = models.IntegerField('데이터 건수', null=True, blank=True)
    error_message = models.TextField('오류 메시지', blank=True, default='')

    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, verbose_name='요청자',
    )
    created_at = models.DateTimeField('요청일시', auto_now_add=True)
    completed_at = models.DateTimeField('완료일시', null=True, blank=True)

    class Meta:
        verbose_name = '리포트 파일'
        verbose_name_plural = '리포트 파일'
        db_table = 'report_files'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_report_type_display()} ({self.get_status_display()})'
