"""
거래처 모델 모듈

거래처(Client), 단가 계약(PriceContract), 파레트 보관료(PalletStoragePrice) 모델을 정의합니다.
"""
from django.db import models
from django.conf import settings
from django.core.validators import (
    RegexValidator, MinValueValidator, MaxValueValidator
)
from django.utils import timezone


class WorkType(models.TextChoices):
    """작업 유형 선택지"""
    INBOUND = 'INBOUND', '입고'
    OUTBOUND = 'OUTBOUND', '출고'
    PICKING = 'PICKING', '피킹'
    PACKING = 'PACKING', '패킹'
    LABELING = 'LABELING', '라벨링'
    LOADING = 'LOADING', '상차'
    UNLOADING = 'UNLOADING', '하차'
    INVENTORY = 'INVENTORY', '재고조사'
    SORTING = 'SORTING', '분류작업'
    REPACK = 'REPACK', '재포장'
    OTHER = 'OTHER', '기타'


class Client(models.Model):
    """
    거래처 모델

    물류 서비스를 이용하는 거래처 정보를 관리합니다.
    """

    # 기본 정보
    company_name = models.CharField(
        '회사명',
        max_length=200,
    )
    business_number = models.CharField(
        '사업자등록번호',
        max_length=12,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^\d{3}-?\d{2}-?\d{5}$',
                message='사업자등록번호 형식이 올바르지 않습니다. (예: 123-45-67890)',
            )
        ],
    )

    # 담당자 정보
    contact_person = models.CharField('담당자명', max_length=100)
    contact_phone = models.CharField(
        '담당자 연락처',
        max_length=20,
        validators=[
            RegexValidator(
                regex=r'^01[0-9]-?\d{3,4}-?\d{4}$',
                message='연락처 형식이 올바르지 않습니다. (예: 010-1234-5678)',
            )
        ],
    )
    contact_email = models.EmailField('담당자 이메일')

    # 계약 정보
    contract_start_date = models.DateField(
        '계약 시작일',
        default=timezone.now,
    )
    contract_end_date = models.DateField(
        '계약 종료일',
        null=True,
        blank=True,
        help_text='미입력 시 무기한 계약으로 간주합니다.',
    )

    # 청구서 발송 정보
    invoice_email = models.EmailField('청구서 수신 이메일')
    invoice_day = models.IntegerField(
        '청구서 발송일',
        default=1,
        validators=[
            MinValueValidator(1, message='1 이상의 값을 입력하세요.'),
            MaxValueValidator(28, message='28 이하의 값을 입력하세요.'),
        ],
        help_text='매월 청구서를 발송할 날짜 (1~28일)',
    )

    # 주소 정보
    address = models.CharField('주소', max_length=500, blank=True)
    address_detail = models.CharField('상세 주소', max_length=200, blank=True)

    # 메모 및 상태
    memo = models.TextField('메모', blank=True)
    is_active = models.BooleanField('활성 상태', default=True)

    # 시스템 정보
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='등록자',
        related_name='created_clients',
    )
    created_at = models.DateTimeField('등록일시', auto_now_add=True)
    updated_at = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'clients'
        verbose_name = '거래처'
        verbose_name_plural = '거래처 목록'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company_name'], name='idx_client_company_name'),
            models.Index(fields=['business_number'], name='idx_client_business_number'),
            models.Index(fields=['is_active'], name='idx_client_is_active'),
        ]

    def __str__(self):
        return f"{self.company_name} ({self.business_number})"

    @property
    def is_contract_active(self):
        """계약이 현재 유효한지 확인"""
        today = timezone.now().date()
        if self.contract_start_date > today:
            return False
        if self.contract_end_date is None:
            return True
        return self.contract_end_date >= today

    def get_current_price_contracts(self):
        """현재 유효한 단가 계약 목록 조회"""
        today = timezone.now().date()
        return self.price_contracts.filter(
            valid_from__lte=today,
            valid_to__gte=today,
        )

    def get_current_pallet_storage_price(self):
        """현재 유효한 파레트 보관료 조회"""
        today = timezone.now().date()
        return self.pallet_storage_prices.filter(
            valid_from__lte=today,
            valid_to__gte=today,
        ).first()


class PriceContract(models.Model):
    """
    단가 계약 모델

    거래처별 작업 유형에 대한 단가 계약을 관리합니다.
    """

    # 관계
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        verbose_name='거래처',
        related_name='price_contracts',
    )

    # 작업 단가
    work_type = models.CharField(
        '작업 유형',
        max_length=20,
        choices=WorkType.choices,
    )
    unit_price = models.DecimalField(
        '단가',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    unit = models.CharField('단위', max_length=20, default='건')

    # 유효 기간
    valid_from = models.DateField('적용 시작일', default=timezone.now)
    valid_to = models.DateField('적용 종료일')

    # 메모 및 시스템 정보
    memo = models.TextField('메모', blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='등록자',
        related_name='created_price_contracts',
    )
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'price_contracts'
        verbose_name = '단가 계약'
        verbose_name_plural = '단가 계약 목록'
        ordering = ['-valid_from']
        indexes = [
            models.Index(
                fields=['client', 'work_type', 'valid_from', 'valid_to'],
                name='idx_price_contract_composite',
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['client', 'work_type', 'valid_from'],
                name='uq_price_contract_client_type_from',
            ),
        ]

    def __str__(self):
        return f"{self.client.company_name} - {self.get_work_type_display()} ({self.unit_price}원/{self.unit})"

    @property
    def is_active(self):
        """현재 유효한 계약인지 확인"""
        today = timezone.now().date()
        return self.valid_from <= today <= self.valid_to


class PalletStoragePrice(models.Model):
    """
    파레트 보관료 모델

    거래처별 파레트 보관 단가를 관리합니다.
    """

    # 관계
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        verbose_name='거래처',
        related_name='pallet_storage_prices',
    )

    # 보관료 단가
    daily_price = models.DecimalField(
        '일 단가',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    monthly_price = models.DecimalField(
        '월 단가',
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )

    # 유효 기간
    valid_from = models.DateField('적용 시작일', default=timezone.now)
    valid_to = models.DateField('적용 종료일')

    # 메모 및 시스템 정보
    memo = models.TextField('메모', blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='등록자',
        related_name='created_pallet_prices',
    )
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'pallet_storage_prices'
        verbose_name = '파레트 보관료'
        verbose_name_plural = '파레트 보관료 목록'
        ordering = ['-valid_from']

    def __str__(self):
        return f"{self.client.company_name} - 일 {self.daily_price}원"

    @property
    def is_active(self):
        """현재 유효한지 확인"""
        today = timezone.now().date()
        return self.valid_from <= today <= self.valid_to
