"""
리포트 모델
"""
from django.conf import settings
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


# ============================================================================
# 일일 출고 리포트
# ============================================================================

class DailyParcelReport(models.Model):
    """일일 출고 리포트 (날짜별 1건)"""

    report_date = models.DateField('리포트 날짜', unique=True)
    file_name = models.CharField('업로드 파일명', max_length=200)
    total_orders = models.IntegerField('총 출고건수', default=0)
    single_count = models.IntegerField('단포 건수', default=0)
    combo_count = models.IntegerField('합포 건수', default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='업로드자',
        related_name='parcel_reports',
    )
    created_at = models.DateTimeField('최초 등록', auto_now_add=True)
    updated_at = models.DateTimeField('최종 수정', auto_now=True)

    class Meta:
        verbose_name = '일일 출고 리포트'
        verbose_name_plural = '일일 출고 리포트'
        db_table = 'daily_parcel_reports'
        ordering = ['-report_date']

    def __str__(self):
        return f'{self.report_date} ({self.total_orders}건)'

    @property
    def combo_ratio(self):
        """합포 비율(%)"""
        if self.total_orders == 0:
            return 0
        return round(self.combo_count / self.total_orders * 100, 1)


class DailyParcelBrand(models.Model):
    """리포트 내 브랜드별 상세"""

    report = models.ForeignKey(
        DailyParcelReport,
        on_delete=models.CASCADE,
        related_name='brands',
        verbose_name='리포트',
    )
    brand_name = models.CharField('브랜드', max_length=100)
    single_count = models.IntegerField('단포', default=0)
    combo_count = models.IntegerField('합포', default=0)
    total_count = models.IntegerField('합계', default=0)

    class Meta:
        verbose_name = '브랜드별 출고'
        verbose_name_plural = '브랜드별 출고'
        db_table = 'daily_parcel_brands'
        ordering = ['-total_count']

    def __str__(self):
        return f'{self.brand_name} (단포 {self.single_count} / 합포 {self.combo_count})'

    @property
    def combo_ratio(self):
        if self.total_count == 0:
            return 0
        return round(self.combo_count / self.total_count * 100, 1)
