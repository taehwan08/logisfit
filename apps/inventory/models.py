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


class Location(models.Model):
    """로케이션 (선반/구역)

    바코드 스캔 시 자동 등록됩니다.
    바코드는 저장 시 자동으로 대문자로 변환됩니다.
    """
    barcode = models.CharField('로케이션 바코드', max_length=50, unique=True, db_index=True)
    name = models.CharField('로케이션명', max_length=100, blank=True, default='')
    zone = models.CharField('구역', max_length=50, blank=True, default='')
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
