"""
반품 관리 모델
"""
from django.db import models
from django.utils import timezone


def generate_return_id():
    """반품번호 자동 채번: RT-YYYYMMDD-NNNN"""
    today = timezone.localtime(timezone.now()).strftime('%Y%m%d')
    prefix = f'RT-{today}-'

    last = (
        ReturnOrder.objects
        .filter(return_id__startswith=prefix)
        .order_by('-return_id')
        .values_list('return_id', flat=True)
        .first()
    )
    seq = int(last.split('-')[-1]) + 1 if last else 1
    return f'{prefix}{seq:04d}'


class ReturnOrder(models.Model):
    """반품 주문"""

    STATUS_CHOICES = [
        ('RECEIVED', '접수'),
        ('INSPECTING', '검수중'),
        ('COMPLETED', '완료'),
    ]

    STATUS_TRANSITIONS = {
        'RECEIVED': 'INSPECTING',
        'INSPECTING': 'COMPLETED',
    }

    REASON_CHOICES = [
        ('CUSTOMER_CHANGE', '고객변심'),
        ('DEFECT', '불량'),
        ('WRONG_DELIVERY', '오배송'),
        ('OTHER', '기타'),
    ]

    return_id = models.CharField(
        '반품번호', max_length=20, unique=True, db_index=True,
    )
    original_order = models.ForeignKey(
        'waves.OutboundOrder', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='return_orders', verbose_name='원주문',
    )
    client = models.ForeignKey(
        'clients.Client', on_delete=models.CASCADE,
        related_name='return_orders', verbose_name='거래처',
    )
    brand = models.ForeignKey(
        'clients.Brand', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='return_orders', verbose_name='브랜드',
    )
    status = models.CharField(
        '상태', max_length=20, choices=STATUS_CHOICES, default='RECEIVED',
    )
    return_reason = models.CharField(
        '반품사유', max_length=20, choices=REASON_CHOICES,
    )
    notes = models.TextField('비고', blank=True, default='')

    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, verbose_name='등록자',
    )
    created_at = models.DateTimeField('등록일시', auto_now_add=True)
    updated_at = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        verbose_name = '반품주문'
        verbose_name_plural = '반품주문'
        db_table = 'return_orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['client', 'status'],
                name='idx_return_client_status',
            ),
        ]

    def __str__(self):
        return f'{self.return_id} ({self.get_status_display()})'

    def save(self, *args, **kwargs):
        if not self.return_id:
            self.return_id = generate_return_id()
        super().save(*args, **kwargs)


class ReturnOrderItem(models.Model):
    """반품 주문 품목"""

    DISPOSITION_CHOICES = [
        ('RESTOCK', '재입고'),
        ('DEFECT_ZONE', '불량존'),
        ('DISPOSE', '폐기'),
    ]

    return_order = models.ForeignKey(
        ReturnOrder, on_delete=models.CASCADE,
        related_name='items', verbose_name='반품주문',
    )
    product = models.ForeignKey(
        'inventory.Product', on_delete=models.CASCADE,
        related_name='return_items', verbose_name='상품',
    )
    qty = models.IntegerField('반품수량')
    good_qty = models.IntegerField('양품수량', default=0)
    defect_qty = models.IntegerField('불량수량', default=0)
    disposition = models.CharField(
        '처리방식', max_length=20, choices=DISPOSITION_CHOICES,
        blank=True, default='',
    )

    class Meta:
        verbose_name = '반품주문 품목'
        verbose_name_plural = '반품주문 품목'
        db_table = 'return_order_items'

    def __str__(self):
        return f'{self.return_order.return_id} - {self.product} ({self.qty})'
