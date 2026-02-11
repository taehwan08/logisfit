"""
검수 시스템 모델
"""
from django.db import models


class UploadBatch(models.Model):
    """업로드 배치 (파일 단위 업로드 이력)"""
    file_name = models.CharField('파일명', max_length=200)
    print_order = models.CharField('출력차수', max_length=100, blank=True, default='')
    delivery_memo = models.CharField('배송메모', max_length=200, blank=True, default='')
    total_orders = models.IntegerField('송장 수', default=0)
    total_products = models.IntegerField('상품 수', default=0)
    uploaded_at = models.DateTimeField('업로드 시간', auto_now_add=True)
    uploaded_by = models.CharField('업로드자', max_length=50, blank=True, default='')

    class Meta:
        db_table = 'upload_batches'
        verbose_name = '업로드 이력'
        verbose_name_plural = '업로드 이력 목록'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.file_name} ({self.uploaded_at.strftime("%Y-%m-%d %H:%M")})'


class Order(models.Model):
    """송장 테이블"""
    upload_batch = models.ForeignKey(
        UploadBatch, on_delete=models.CASCADE, related_name='orders',
        null=True, blank=True, verbose_name='업로드 배치'
    )
    tracking_number = models.CharField('송장번호', max_length=50, unique=True, db_index=True)
    seller = models.CharField('판매처', max_length=100)
    receiver_name = models.CharField('수령인', max_length=100)
    receiver_phone = models.CharField('핸드폰', max_length=20)
    receiver_address = models.TextField('주소')
    registered_date = models.CharField('등록일', max_length=50, blank=True, default='')
    courier = models.CharField('택배사', max_length=50, blank=True, default='')
    print_order = models.CharField('출력차수', max_length=100, blank=True, default='')
    delivery_memo = models.CharField('배송메모', max_length=200, blank=True, default='')
    status = models.CharField('상태', max_length=20, default='대기중', choices=[
        ('대기중', '대기중'),
        ('검수중', '검수중'),
        ('완료', '완료'),
    ])
    uploaded_at = models.DateTimeField('업로드 시간', auto_now_add=True)
    completed_at = models.DateTimeField('검수 완료 시간', null=True, blank=True)

    class Meta:
        db_table = 'orders'
        indexes = [
            models.Index(fields=['status']),
        ]
        verbose_name = '송장'
        verbose_name_plural = '송장 목록'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.tracking_number} ({self.receiver_name})'


class OrderProduct(models.Model):
    """주문 상품 테이블"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='products')
    barcode = models.CharField('상품바코드', max_length=50, db_index=True)
    product_name = models.CharField('상품명', max_length=200)
    quantity = models.IntegerField('주문수량')
    scanned_quantity = models.IntegerField('스캔수량', default=0)

    class Meta:
        db_table = 'order_products'
        indexes = [
            models.Index(fields=['barcode']),
        ]
        verbose_name = '주문 상품'
        verbose_name_plural = '주문 상품 목록'

    def __str__(self):
        return f'{self.product_name} ({self.barcode})'


class InspectionLog(models.Model):
    """검수 로그 테이블"""
    SCAN_TYPE_CHOICES = [
        ('송장', '송장'),
        ('상품', '상품'),
    ]
    ALERT_CODE_CHOICES = [
        ('정상', '정상'),
        ('숫자', '숫자'),
        ('완료', '완료'),
        ('스캔오류', '스캔오류'),
        ('송장번호미등록', '송장번호미등록'),
        ('기처리배송', '기처리배송'),
        ('중복스캔', '중복스캔'),
        ('상품오류', '상품오류'),
    ]

    tracking_number = models.CharField('송장번호', max_length=50)
    barcode = models.CharField('상품바코드', max_length=50, null=True, blank=True)
    scan_type = models.CharField('스캔타입', max_length=20, choices=SCAN_TYPE_CHOICES)
    alert_code = models.CharField('알림코드', max_length=20, choices=ALERT_CODE_CHOICES)
    worker = models.CharField('작업자', max_length=50, null=True, blank=True)
    created_at = models.DateTimeField('스캔 시간', auto_now_add=True)

    class Meta:
        db_table = 'inspection_logs'
        indexes = [
            models.Index(fields=['tracking_number']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = '검수 로그'
        verbose_name_plural = '검수 로그 목록'
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.alert_code}] {self.tracking_number} - {self.scan_type}'
