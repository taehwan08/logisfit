"""
이력 관리 모델

모든 재고 변동을 기록하는 트랜잭션 로그 테이블입니다.
"""
from django.db import models


class InventoryTransaction(models.Model):
    """재고 트랜잭션

    모든 재고 변동(입고, 출고, 이동, 조정, 할당, 반품 등)을 기록합니다.
    읽기 전용으로 운영하며, 삭제를 허용하지 않습니다.
    """

    TRANSACTION_TYPES = [
        ('GR', '입고'),
        ('GI', '출고'),
        ('MV', '로케이션 이동'),
        ('ADJ_PLUS', '재고 조정(증가)'),
        ('ADJ_MINUS', '재고 조정(감소)'),
        ('ALC', '할당'),
        ('ALC_R', '할당 해제'),
        ('RTN', '반품 입고'),
        ('WV_MV', '웨이브 이동'),
    ]

    REFERENCE_TYPES = [
        ('INBOUND', '입고'),
        ('OUTBOUND', '출고'),
        ('WAVE', '웨이브'),
        ('ADJUSTMENT', '조정'),
        ('RETURN', '반품'),
        ('MANUAL', '수동'),
        ('CYCLE_COUNT', '재고실사'),
    ]

    timestamp = models.DateTimeField('발생일시', auto_now_add=True, db_index=True)
    client = models.ForeignKey(
        'clients.Client', on_delete=models.CASCADE,
        related_name='inventory_transactions', verbose_name='거래처',
        db_index=True,
    )
    brand = models.ForeignKey(
        'clients.Brand', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='inventory_transactions', verbose_name='브랜드',
    )
    product = models.ForeignKey(
        'inventory.Product', on_delete=models.CASCADE,
        related_name='transactions', verbose_name='상품',
    )

    transaction_type = models.CharField(
        '트랜잭션 유형', max_length=10, choices=TRANSACTION_TYPES,
    )
    from_location = models.ForeignKey(
        'inventory.Location', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='transactions_from', verbose_name='출발 로케이션',
    )
    to_location = models.ForeignKey(
        'inventory.Location', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='transactions_to', verbose_name='도착 로케이션',
    )

    qty = models.IntegerField('변동 수량')
    balance_after = models.IntegerField('변동 후 잔량')

    reference_type = models.CharField(
        '참조 유형', max_length=20, choices=REFERENCE_TYPES,
    )
    reference_id = models.CharField(
        '참조번호', max_length=100, blank=True, default='',
    )
    reason = models.CharField('사유', max_length=200, blank=True, default='')

    performed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, verbose_name='수행자',
    )

    class Meta:
        verbose_name = '재고 트랜잭션'
        verbose_name_plural = '재고 트랜잭션'
        db_table = 'inventory_transactions'
        ordering = ['-timestamp']
        indexes = [
            models.Index(
                fields=['timestamp', 'client'],
                name='idx_txn_timestamp_client',
            ),
            models.Index(
                fields=['product', 'timestamp'],
                name='idx_txn_product_timestamp',
            ),
            models.Index(
                fields=['reference_type', 'reference_id'],
                name='idx_txn_ref_type_id',
            ),
            models.Index(
                fields=['client', 'transaction_type', 'timestamp'],
                name='idx_txn_client_type_ts',
            ),
        ]

    def __str__(self):
        return (
            f'[{self.get_transaction_type_display()}] '
            f'{self.product} {self.qty:+d} → {self.balance_after}'
        )


def log_transaction(*, client, product, transaction_type, qty, balance_after,
                    from_location=None, to_location=None, brand=None,
                    reference_type, reference_id='', reason='',
                    performed_by=None):
    """재고 트랜잭션 기록 (모든 재고 변동 시 호출)"""
    return InventoryTransaction.objects.create(
        client=client, brand=brand, product=product,
        transaction_type=transaction_type,
        from_location=from_location, to_location=to_location,
        qty=qty, balance_after=balance_after,
        reference_type=reference_type, reference_id=reference_id,
        reason=reason, performed_by=performed_by,
    )
