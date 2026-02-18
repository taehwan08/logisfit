"""
재고 관리 모델
"""
from django.db import models


class Product(models.Model):
    """상품 마스터

    바코드-상품명 매핑 테이블. 일괄 등록(엑셀) 또는 수동 등록 가능.
    재고 스캔 시 바코드를 입력하면 자동으로 상품명이 표시됩니다.
    """
    barcode = models.CharField('바코드', max_length=50, unique=True, db_index=True)
    name = models.CharField('상품명', max_length=200)
    created_at = models.DateTimeField('등록일시', auto_now_add=True)
    updated_at = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'products'
        verbose_name = '상품'
        verbose_name_plural = '상품 목록'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.barcode})'


class Location(models.Model):
    """로케이션 (선반/구역)

    바코드 스캔 시 자동 등록됩니다.
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
