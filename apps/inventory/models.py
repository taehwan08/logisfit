"""
재고 관리 모델
"""
from django.db import models


class Product(models.Model):
    """상품 마스터

    바코드-상품명 매핑 테이블. 일괄 등록(엑셀) 또는 수동 등록 가능.
    재고 스캔 시 바코드를 입력하면 자동으로 상품명이 표시됩니다.
    """
    barcode = models.CharField('바코드', max_length=50, db_index=True)
    name = models.CharField('상품명', max_length=200)
    display_name = models.CharField('관리명', max_length=200, blank=True, default='')
    option_code = models.CharField('옵션코드', max_length=50, blank=True, default='', db_index=True)
    client = models.ForeignKey(
        'clients.Client', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='products', verbose_name='거래처',
    )
    brand = models.ForeignKey(
        'clients.Brand', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='products', verbose_name='브랜드',
    )

    # 물류 속성
    weight = models.DecimalField(
        '중량(g)', max_digits=10, decimal_places=2,
        null=True, blank=True,
    )
    dimensions = models.JSONField(
        '규격(L/W/H)', null=True, blank=True,
    )
    cbm = models.DecimalField(
        'CBM', max_digits=10, decimal_places=6,
        null=True, blank=True,
    )
    category = models.CharField(
        '카테고리', max_length=100, blank=True, default='',
    )
    is_set = models.BooleanField('세트상품 여부', default=False)

    created_at = models.DateTimeField('등록일시', auto_now_add=True)
    updated_at = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'products'
        verbose_name = '상품'
        verbose_name_plural = '상품 목록'
        ordering = ['name']
        unique_together = [['barcode', 'name']]

    def __str__(self):
        return f'{self.name} ({self.barcode})'


class ProductBarcode(models.Model):
    """상품 바코드 (1:N)

    하나의 상품에 여러 바코드(대표, 보조, 박스 바코드 등)를 연결합니다.
    기존 Product.barcode 필드는 하위호환을 위해 유지됩니다.
    """

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE,
        related_name='barcodes', verbose_name='상품',
    )
    barcode = models.CharField('바코드', max_length=100, unique=True, db_index=True)
    is_primary = models.BooleanField('대표 바코드', default=False)

    class Meta:
        db_table = 'product_barcodes'
        verbose_name = '상품 바코드'
        verbose_name_plural = '상품 바코드 목록'

    def __str__(self):
        primary = ' [대표]' if self.is_primary else ''
        return f'{self.product.name} - {self.barcode}{primary}'


class SetProduct(models.Model):
    """세트상품 구성

    세트 상품(parent)을 구성하는 단품(child)과 수량을 정의합니다.
    """

    parent = models.ForeignKey(
        Product, on_delete=models.CASCADE,
        related_name='set_children', verbose_name='세트 상품',
    )
    child = models.ForeignKey(
        Product, on_delete=models.CASCADE,
        related_name='set_parents', verbose_name='구성 단품',
    )
    qty = models.IntegerField('구성 수량', default=1)

    class Meta:
        db_table = 'set_products'
        verbose_name = '세트상품 구성'
        verbose_name_plural = '세트상품 구성 목록'
        unique_together = ['parent', 'child']

    def __str__(self):
        return f'{self.parent.name} → {self.child.name} x{self.qty}'


class Location(models.Model):
    """로케이션 (선반/구역)

    바코드 스캔 시 자동 등록됩니다.
    바코드는 저장 시 자동으로 대문자로 변환됩니다.
    """

    ZONE_TYPE_CHOICES = [
        ('INBOUND_STAGING', '입고 스테이징'),
        ('STORAGE', '보관존'),
        ('PICKING', '피킹존'),
        ('OUTBOUND_STAGING', '출고존'),
        ('DEFECT', '불량존'),
        ('RETURN', '반품존'),
    ]

    barcode = models.CharField('로케이션 바코드', max_length=50, unique=True, db_index=True)
    name = models.CharField('로케이션명', max_length=100, blank=True, default='')
    zone = models.CharField('구역', max_length=50, blank=True, default='')
    zone_type = models.CharField(
        '구역 유형',
        max_length=20,
        choices=ZONE_TYPE_CHOICES,
        default='STORAGE',
    )
    is_active = models.BooleanField('활성 여부', default=True)
    max_capacity = models.IntegerField('최대 적재량', null=True, blank=True)
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'locations'
        verbose_name = '로케이션'
        verbose_name_plural = '로케이션 목록'
        ordering = ['barcode']

    def save(self, *args, **kwargs):
        if self.barcode:
            self.barcode = self.barcode.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.name:
            return f'{self.barcode} ({self.name})'
        return self.barcode


class InventorySession(models.Model):
    """재고조사 세션

    관리자가 시작/종료하며, 세션이 활성 상태일 때만 스캔 입력이 가능합니다.
    """
    STATUS_CHOICES = [
        ('active', '진행중'),
        ('closed', '종료'),
    ]

    name = models.CharField('세션명', max_length=100)
    status = models.CharField('상태', max_length=10, choices=STATUS_CHOICES, default='active')
    started_at = models.DateTimeField('시작일시', auto_now_add=True)
    ended_at = models.DateTimeField('종료일시', null=True, blank=True)
    started_by = models.CharField('시작자', max_length=50, blank=True, default='')

    class Meta:
        db_table = 'inventory_sessions'
        verbose_name = '재고조사 세션'
        verbose_name_plural = '재고조사 세션 목록'
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.name} ({self.get_status_display()})'


class InventoryRecord(models.Model):
    """재고 기록

    세션 × 로케이션 × 상품 단위의 재고 기록입니다.
    """
    session = models.ForeignKey(
        InventorySession, on_delete=models.CASCADE,
        related_name='records', verbose_name='세션'
    )
    location = models.ForeignKey(
        Location, on_delete=models.CASCADE,
        related_name='records', verbose_name='로케이션'
    )
    barcode = models.CharField('상품바코드', max_length=50, db_index=True)
    product_name = models.CharField('상품명', max_length=200, blank=True, default='')
    quantity = models.IntegerField('수량', default=1)
    expiry_date = models.CharField('유통기한', max_length=20, blank=True, default='')
    lot_number = models.CharField('로트번호', max_length=50, blank=True, default='')
    worker = models.CharField('작업자', max_length=50, blank=True, default='')
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'inventory_records'
        indexes = [
            models.Index(fields=['barcode']),
            models.Index(fields=['session', 'location']),
        ]
        verbose_name = '재고 기록'
        verbose_name_plural = '재고 기록 목록'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.location.barcode} - {self.barcode} ({self.quantity}개)'


class InboundRecord(models.Model):
    """입고 기록

    상품 입고 시 수량, 유통기한, 로트번호를 기록합니다.
    등록 후 슬랙 알림이 전송되며, 관리자가 전산 등록 완료 처리합니다.
    """
    STATUS_CHOICES = [
        ('pending', '대기'),
        ('completed', '전산등록완료'),
    ]

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE,
        related_name='inbound_records', verbose_name='상품'
    )
    quantity = models.IntegerField('입고수량')
    expiry_date = models.CharField('유통기한', max_length=20, blank=True, default='')
    lot_number = models.CharField('로트번호', max_length=50, blank=True, default='')
    status = models.CharField('상태', max_length=20, choices=STATUS_CHOICES, default='pending')
    memo = models.TextField('메모', blank=True, default='')

    registered_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='inbound_registered', verbose_name='등록자'
    )
    completed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inbound_completed', verbose_name='전산처리자'
    )
    completed_at = models.DateTimeField('전산처리일시', null=True, blank=True)

    created_at = models.DateTimeField('등록일시', auto_now_add=True)
    updated_at = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'inbound_records'
        ordering = ['-created_at']
        verbose_name = '입고 기록'
        verbose_name_plural = '입고 기록 목록'

    def __str__(self):
        return f'{self.product.name} ({self.quantity}개) - {self.get_status_display()}'


class InboundImage(models.Model):
    """입고 이미지

    입고 기록에 첨부된 이미지입니다.
    하나의 입고 기록에 여러 장의 이미지를 첨부할 수 있습니다.
    """
    inbound_record = models.ForeignKey(
        InboundRecord, on_delete=models.CASCADE,
        related_name='images', verbose_name='입고 기록'
    )
    image = models.ImageField('이미지', upload_to='inbound/%Y/%m/')
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'inbound_images'
        ordering = ['created_at']
        verbose_name = '입고 이미지'
        verbose_name_plural = '입고 이미지 목록'

    def __str__(self):
        return f'입고이미지 #{self.pk} (입고기록 #{self.inbound_record_id})'


class InventoryBalance(models.Model):
    """재고 잔량 (5단 재고 구조)

    상품 × 로케이션 × 거래처 × 로트 단위로 실물/할당/예약 재고를 관리합니다.
    가용재고 = 실물재고 - 할당재고 - 예약재고

    기존 InventoryRecord는 실사(재고조사) 용도로 유지됩니다.
    """

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE,
        related_name='balances', verbose_name='상품',
    )
    location = models.ForeignKey(
        Location, on_delete=models.CASCADE,
        related_name='balances', verbose_name='로케이션',
    )
    client = models.ForeignKey(
        'clients.Client', on_delete=models.CASCADE,
        related_name='inventory_balances', verbose_name='거래처',
    )

    on_hand_qty = models.IntegerField('실물재고', default=0)
    allocated_qty = models.IntegerField('할당재고', default=0)
    reserved_qty = models.IntegerField('예약재고', default=0)

    lot_number = models.CharField('로트번호', max_length=100, blank=True, default='')
    expiry_date = models.DateField('유통기한', null=True, blank=True)

    updated_at = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        verbose_name = '재고 잔량'
        verbose_name_plural = '재고 잔량'
        db_table = 'inventory_balances'
        unique_together = ['product', 'location', 'client', 'lot_number']
        indexes = [
            models.Index(
                fields=['client', 'product'],
                name='idx_balance_client_product',
            ),
            models.Index(
                fields=['location'],
                name='idx_balance_location',
            ),
            models.Index(
                fields=['client'],
                name='idx_balance_client',
            ),
        ]

    @property
    def available_qty(self):
        """가용재고 = 실물 - 할당 - 예약"""
        return self.on_hand_qty - self.allocated_qty - self.reserved_qty

    def __str__(self):
        return f'{self.client} | {self.product} @ {self.location} : {self.on_hand_qty}'


class SafetyStock(models.Model):
    """안전재고

    상품 × 거래처 단위로 최소 유지 수량을 설정합니다.
    알림 활성화 시 실물재고가 최소 수량 미만이면 알림을 발송합니다.
    """

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE,
        related_name='safety_stocks', verbose_name='상품',
    )
    client = models.ForeignKey(
        'clients.Client', on_delete=models.CASCADE,
        related_name='safety_stocks', verbose_name='거래처',
    )
    min_qty = models.IntegerField('최소 유지 수량')
    alert_enabled = models.BooleanField('알림 활성화', default=True)

    class Meta:
        verbose_name = '안전재고'
        verbose_name_plural = '안전재고'
        db_table = 'safety_stocks'
        unique_together = ['product', 'client']

    def __str__(self):
        return f'{self.client} | {self.product} : 최소 {self.min_qty}'


class ReservedStock(models.Model):
    """예약재고

    특정 사유로 일시적으로 묶어둔 재고입니다.
    해제 시 released_at을 기록하고 is_active를 False로 변경합니다.
    """

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE,
        related_name='reserved_stocks', verbose_name='상품',
    )
    client = models.ForeignKey(
        'clients.Client', on_delete=models.CASCADE,
        related_name='reserved_stocks', verbose_name='거래처',
    )
    brand = models.ForeignKey(
        'clients.Brand', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reserved_stocks', verbose_name='브랜드',
    )
    reserved_qty = models.IntegerField('예약 수량')
    reason = models.CharField('사유', max_length=200)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, verbose_name='등록자',
    )
    created_at = models.DateTimeField('등록일시', auto_now_add=True)
    released_at = models.DateTimeField('해제 일시', null=True, blank=True)
    is_active = models.BooleanField('활성 여부', default=True)

    class Meta:
        verbose_name = '예약재고'
        verbose_name_plural = '예약재고'
        db_table = 'reserved_stocks'
        ordering = ['-created_at']

    def __str__(self):
        status = '활성' if self.is_active else '해제'
        return f'{self.client} | {self.product} : {self.reserved_qty} ({status})'


def check_safety_stock_alerts(client_id=None):
    """안전재고 미달 상품 목록 반환

    InventoryBalance의 on_hand_qty 합계와 SafetyStock.min_qty를 비교하여
    미달 상품 리스트를 반환합니다.

    Args:
        client_id: 특정 거래처 ID (None이면 전체 조회)

    Returns:
        list[dict]: 미달 상품 목록
            - safety_stock: SafetyStock 인스턴스
            - total_on_hand: 실물재고 합계
            - shortage: 부족 수량
    """
    from django.db.models import Sum

    qs = SafetyStock.objects.filter(alert_enabled=True).select_related(
        'product', 'client',
    )
    if client_id:
        qs = qs.filter(client_id=client_id)

    alerts = []
    for ss in qs:
        total = InventoryBalance.objects.filter(
            product=ss.product,
            client=ss.client,
        ).aggregate(total=Sum('on_hand_qty'))['total'] or 0

        if total < ss.min_qty:
            alerts.append({
                'safety_stock': ss,
                'total_on_hand': total,
                'shortage': ss.min_qty - total,
            })

    return alerts
