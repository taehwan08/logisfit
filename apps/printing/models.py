"""
출력 관리 모델

프린터, 택배사, 송장 출력 작업을 관리합니다.
"""
from django.db import models


class Printer(models.Model):
    """프린터"""

    PRINTER_TYPES = [
        ('ZEBRA', 'Zebra'),
        ('SATO', 'SATO'),
        ('TSC', 'TSC'),
    ]
    LANGUAGE_CHOICES = [
        ('ZPL', 'ZPL'),
        ('SBPL', 'SBPL'),
        ('TSPL', 'TSPL'),
    ]

    name = models.CharField('프린터명', max_length=100)
    ip_address = models.GenericIPAddressField('IP 주소', default='0.0.0.0')
    port = models.IntegerField('포트', default=9100)
    printer_type = models.CharField(
        '프린터 유형', max_length=10, choices=PRINTER_TYPES, default='ZEBRA',
    )
    printer_language = models.CharField(
        '프린터 언어', max_length=10, choices=LANGUAGE_CHOICES, default='ZPL',
    )
    is_active = models.BooleanField('활성 상태', default=True)
    location_description = models.CharField(
        '설치 위치', max_length=100, blank=True, default='',
    )
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        verbose_name = '프린터'
        verbose_name_plural = '프린터 목록'
        db_table = 'printers'

    def __str__(self):
        return f'{self.name} ({self.ip_address}:{self.port})'


class Carrier(models.Model):
    """택배사"""

    name = models.CharField('택배사명', max_length=50)
    code = models.CharField('택배사 코드', max_length=20, unique=True)
    api_config = models.JSONField('API 설정', default=dict)
    label_template = models.TextField('라벨 템플릿', blank=True, default='')
    is_active = models.BooleanField('활성 상태', default=True)
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        verbose_name = '택배사'
        verbose_name_plural = '택배사 목록'
        db_table = 'carriers'

    def __str__(self):
        return self.name


class PrintJob(models.Model):
    """송장 출력 작업"""

    STATUS_CHOICES = [
        ('PENDING', '대기'),
        ('PRINTED', '출력완료'),
        ('FAILED', '실패'),
    ]

    order = models.ForeignKey(
        'waves.OutboundOrder', on_delete=models.CASCADE,
        related_name='print_jobs', verbose_name='출고주문',
    )
    printer = models.ForeignKey(
        Printer, on_delete=models.SET_NULL,
        null=True, verbose_name='프린터',
    )
    tracking_number = models.CharField('송장번호', max_length=50)
    carrier = models.ForeignKey(
        Carrier, on_delete=models.SET_NULL,
        null=True, verbose_name='택배사',
    )
    status = models.CharField(
        '상태', max_length=10, choices=STATUS_CHOICES, default='PENDING',
    )
    attempts = models.IntegerField('시도 횟수', default=0)
    printed_at = models.DateTimeField('출력일시', null=True, blank=True)
    printed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='출력자',
    )
    error_message = models.TextField('오류 메시지', blank=True, default='')
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        verbose_name = '출력 작업'
        verbose_name_plural = '출력 작업 목록'
        db_table = 'print_jobs'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.order.wms_order_id} - {self.get_status_display()}'
