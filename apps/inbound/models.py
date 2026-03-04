"""
입고 관리 모델
"""
from django.db import models
from django.utils import timezone


def generate_inbound_id():
    """입고번호 자동 채번: IB-YYYYMMDD-NNNN"""
    today = timezone.localtime(timezone.now()).strftime('%Y%m%d')
    prefix = f'IB-{today}-'

    last = (
        InboundOrder.objects
        .filter(inbound_id__startswith=prefix)
        .order_by('-inbound_id')
        .values_list('inbound_id', flat=True)
        .first()
    )
    if last:
        seq = int(last.split('-')[-1]) + 1
    else:
        seq = 1

    return f'{prefix}{seq:04d}'


class InboundOrder(models.Model):
    """입고예정

    화주사가 입고 예정 정보를 등록하면, 현장에서 도착→검수→적치 순으로 처리합니다.
    """

    STATUS_CHOICES = [
        ('PLANNED', '예정'),
        ('ARRIVED', '도착'),
        ('INSPECTING', '검수중'),
        ('INSPECTED', '검수완료'),
        ('PUTAWAY_COMPLETE', '적치완료'),
    ]

    # 유효 상태 전이 매핑
    STATUS_TRANSITIONS = {
        'PLANNED': 'ARRIVED',
        'ARRIVED': 'INSPECTING',
        'INSPECTING': 'INSPECTED',
        'INSPECTED': 'PUTAWAY_COMPLETE',
    }

    inbound_id = models.CharField(
        '입고번호', max_length=20, unique=True, db_index=True,
    )
    client = models.ForeignKey(
        'clients.Client', on_delete=models.CASCADE,
        related_name='inbound_orders', verbose_name='거래처',
    )
    brand = models.ForeignKey(
        'clients.Brand', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='inbound_orders', verbose_name='브랜드',
    )
    status = models.CharField(
        '상태', max_length=20, choices=STATUS_CHOICES, default='PLANNED',
    )
    expected_date = models.DateField('입고예정일')
    notes = models.TextField('비고', blank=True, default='')

    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, verbose_name='등록자',
    )
    created_at = models.DateTimeField('등록일시', auto_now_add=True)
    updated_at = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        verbose_name = '입고예정'
        verbose_name_plural = '입고예정'
        db_table = 'inbound_orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['client', 'status'],
                name='idx_inbound_client_status',
            ),
            models.Index(
                fields=['expected_date'],
                name='idx_inbound_expected_date',
            ),
        ]

    def __str__(self):
        return f'{self.inbound_id} ({self.get_status_display()})'

    def save(self, *args, **kwargs):
        if not self.inbound_id:
            self.inbound_id = generate_inbound_id()
        super().save(*args, **kwargs)


class InboundOrderItem(models.Model):
    """입고예정 품목

    입고 예정 수량과 실제 검수 수량, 불량 수량을 기록합니다.
    """

    inbound_order = models.ForeignKey(
        InboundOrder, on_delete=models.CASCADE,
        related_name='items', verbose_name='입고예정',
    )
    product = models.ForeignKey(
        'inventory.Product', on_delete=models.CASCADE,
        related_name='inbound_items', verbose_name='상품',
    )
    expected_qty = models.IntegerField('예정수량')
    inspected_qty = models.IntegerField('검수수량', default=0)
    defect_qty = models.IntegerField('불량수량', default=0)
    putaway_location = models.ForeignKey(
        'inventory.Location', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='inbound_items', verbose_name='적치 로케이션',
    )
    lot_number = models.CharField('로트번호', max_length=100, blank=True, default='')
    expiry_date = models.DateField('유통기한', null=True, blank=True)

    class Meta:
        verbose_name = '입고예정 품목'
        verbose_name_plural = '입고예정 품목'
        db_table = 'inbound_order_items'

    def __str__(self):
        return f'{self.inbound_order.inbound_id} - {self.product} ({self.expected_qty})'
