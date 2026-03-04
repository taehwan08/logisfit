"""
웨이브 관리 모델

출고 주문(OutboundOrder)과 웨이브(Wave) 배치 관리.
"""
from django.db import models
from django.utils import timezone


def generate_wave_id():
    """웨이브번호 자동 채번: WV-YYYYMMDD-NN (2자리 시퀀스, 일별 리셋)"""
    today = timezone.localtime(timezone.now()).strftime('%Y%m%d')
    prefix = f'WV-{today}-'

    last = (
        Wave.objects
        .filter(wave_id__startswith=prefix)
        .order_by('-wave_id')
        .values_list('wave_id', flat=True)
        .first()
    )
    if last:
        seq = int(last.split('-')[-1]) + 1
    else:
        seq = 1

    return f'{prefix}{seq:02d}'


def generate_wms_order_id():
    """WMS 주문번호 자동 채번: WO-YYYYMMDD-NNNNN (5자리 시퀀스, 일별 리셋)"""
    today = timezone.localtime(timezone.now()).strftime('%Y%m%d')
    prefix = f'WO-{today}-'

    last = (
        OutboundOrder.objects
        .filter(wms_order_id__startswith=prefix)
        .order_by('-wms_order_id')
        .values_list('wms_order_id', flat=True)
        .first()
    )
    if last:
        seq = int(last.split('-')[-1]) + 1
    else:
        seq = 1

    return f'{prefix}{seq:05d}'


class Wave(models.Model):
    """웨이브 배치

    ALLOCATED 주문들을 묶어 피킹 → 분배 → 출고 단위로 관리합니다.
    """

    STATUS_CHOICES = [
        ('CREATED', '생성'),
        ('PICKING', '피킹중'),
        ('DISTRIBUTING', '분배중'),
        ('SHIPPING', '출고중'),
        ('COMPLETED', '완료'),
    ]

    wave_id = models.CharField('웨이브번호', max_length=20, unique=True)
    status = models.CharField(
        '상태', max_length=20, choices=STATUS_CHOICES, default='CREATED',
    )
    wave_time = models.CharField('웨이브 시간', max_length=5, default='')
    outbound_zone = models.ForeignKey(
        'inventory.Location', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='출고존',
    )

    total_orders = models.IntegerField('총 주문수', default=0)
    total_skus = models.IntegerField('총 SKU수', default=0)
    picked_count = models.IntegerField('피킹완료 주문수', default=0)
    inspected_count = models.IntegerField('검수완료 주문수', default=0)
    shipped_count = models.IntegerField('출고완료 주문수', default=0)

    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        verbose_name='생성자',
    )
    created_at = models.DateTimeField('생성일시', auto_now_add=True)
    completed_at = models.DateTimeField('완료일시', null=True, blank=True)

    class Meta:
        verbose_name = '웨이브'
        verbose_name_plural = '웨이브'
        db_table = 'waves'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.wave_id} ({self.get_status_display()})'

    def save(self, *args, **kwargs):
        if not self.wave_id:
            self.wave_id = generate_wave_id()
        super().save(*args, **kwargs)


class OutboundOrder(models.Model):
    """출고주문

    외부 OMS/사방넷/카페24 등에서 수신한 주문을 WMS 내부에서 관리합니다.
    접수 → 할당 → 피킹 → 검수 → 출고 순으로 처리합니다.
    """

    STATUS_CHOICES = [
        ('RECEIVED', '접수'),
        ('ALLOCATED', '할당완료'),
        ('PICKING', '피킹중'),
        ('INSPECTED', '검수완료'),
        ('SHIPPED', '출고완료'),
        ('HELD', '보류'),
        ('CANCELLED', '취소'),
    ]

    ORDER_TYPE_CHOICES = [
        ('B2C', 'B2C'),
        ('B2B', 'B2B'),
    ]

    wms_order_id = models.CharField(
        'WMS주문번호', max_length=30, unique=True,
    )
    source = models.CharField('주문출처', max_length=30)
    source_order_id = models.CharField(
        '원본주문번호', max_length=100, db_index=True,
    )

    client = models.ForeignKey(
        'clients.Client', on_delete=models.CASCADE,
        related_name='outbound_orders', verbose_name='거래처',
    )
    brand = models.ForeignKey(
        'clients.Brand', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='outbound_orders', verbose_name='브랜드',
    )
    order_type = models.CharField(
        '주문유형', max_length=10, choices=ORDER_TYPE_CHOICES, default='B2C',
    )
    status = models.CharField(
        '상태', max_length=20, choices=STATUS_CHOICES, default='RECEIVED',
    )

    recipient_name = models.CharField('수취인', max_length=100)
    recipient_phone = models.CharField('연락처', max_length=20)
    recipient_address = models.TextField('배송지')
    recipient_zip = models.CharField(
        '우편번호', max_length=10, blank=True, default='',
    )
    shipping_memo = models.TextField('배송메모', blank=True, default='')

    wave = models.ForeignKey(
        Wave, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='orders', verbose_name='웨이브',
    )
    tracking_number = models.CharField(
        '송장번호', max_length=50, blank=True, default='',
    )
    carrier = models.ForeignKey(
        'printing.Carrier', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='택배사',
    )

    hold_reason = models.CharField(
        '보류사유', max_length=200, blank=True, default='',
    )
    ordered_at = models.DateTimeField('주문일시')
    shipped_at = models.DateTimeField('출고일시', null=True, blank=True)
    created_at = models.DateTimeField('등록일시', auto_now_add=True)
    updated_at = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        verbose_name = '출고주문'
        verbose_name_plural = '출고주문'
        db_table = 'outbound_orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['client', 'status'],
                name='idx_outbound_client_status',
            ),
            models.Index(
                fields=['wave'],
                name='idx_outbound_wave',
            ),
            models.Index(
                fields=['source', 'source_order_id'],
                name='idx_outbound_source',
            ),
        ]

    def __str__(self):
        return f'{self.wms_order_id} ({self.get_status_display()})'

    def save(self, *args, **kwargs):
        if not self.wms_order_id:
            self.wms_order_id = generate_wms_order_id()
        super().save(*args, **kwargs)


class OutboundOrderItem(models.Model):
    """출고주문 품목"""

    order = models.ForeignKey(
        OutboundOrder, on_delete=models.CASCADE,
        related_name='items', verbose_name='출고주문',
    )
    product = models.ForeignKey(
        'inventory.Product', on_delete=models.CASCADE,
        related_name='outbound_items', verbose_name='상품',
    )
    qty = models.IntegerField('주문수량')
    picked_qty = models.IntegerField('피킹수량', default=0)
    inspected_qty = models.IntegerField('검수수량', default=0)
    source_item_id = models.CharField(
        '원본품목ID', max_length=100, blank=True, default='',
    )

    class Meta:
        verbose_name = '출고주문 품목'
        verbose_name_plural = '출고주문 품목'
        db_table = 'outbound_order_items'

    def __str__(self):
        return f'{self.order.wms_order_id} - {self.product} x{self.qty}'


class TotalPickList(models.Model):
    """토탈피킹 리스트

    웨이브 내 주문들의 SKU별 합산 피킹 목록.
    """

    STATUS_CHOICES = [
        ('PENDING', '대기'),
        ('IN_PROGRESS', '진행중'),
        ('COMPLETED', '완료'),
    ]

    wave = models.ForeignKey(
        Wave, on_delete=models.CASCADE,
        related_name='pick_lists', verbose_name='웨이브',
    )
    product = models.ForeignKey(
        'inventory.Product', on_delete=models.CASCADE,
        verbose_name='상품',
    )
    total_qty = models.IntegerField('합산수량')
    picked_qty = models.IntegerField('피킹수량', default=0)
    status = models.CharField(
        '상태', max_length=20, choices=STATUS_CHOICES, default='PENDING',
    )

    class Meta:
        verbose_name = '토탈피킹 리스트'
        verbose_name_plural = '토탈피킹 리스트'
        db_table = 'total_pick_lists'

    def __str__(self):
        return f'{self.wave.wave_id} - {self.product} x{self.total_qty}'


class TotalPickListDetail(models.Model):
    """토탈피킹 상세

    SKU별 어느 로케이션에서 몇 개를 피킹하는지 상세 정보.
    """

    pick_list = models.ForeignKey(
        TotalPickList, on_delete=models.CASCADE,
        related_name='details', verbose_name='피킹리스트',
    )
    from_location = models.ForeignKey(
        'inventory.Location', on_delete=models.CASCADE,
        related_name='+', verbose_name='출발 로케이션',
    )
    to_location = models.ForeignKey(
        'inventory.Location', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='+', verbose_name='도착 로케이션',
    )
    qty = models.IntegerField('수량')
    picked_qty = models.IntegerField('피킹수량', default=0)
    picked_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='피킹 작업자',
    )
    picked_at = models.DateTimeField('피킹일시', null=True, blank=True)

    class Meta:
        verbose_name = '토탈피킹 상세'
        verbose_name_plural = '토탈피킹 상세'
        db_table = 'total_pick_list_details'

    def __str__(self):
        return f'{self.pick_list} @ {self.from_location} x{self.qty}'
