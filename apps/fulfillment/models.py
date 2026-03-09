"""
출고 관리 모델

B2B 출고 주문(발주)을 관리하는 모델을 정의합니다.
다양한 플랫폼(쿠팡, 컬리, 올리브영 등)의 출고 주문을 통합 관리합니다.
"""
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone


class FulfillmentOrder(models.Model):
    """
    출고 주문(발주) 모델

    거래처 → 브랜드 하위 구조로 출고 주문을 관리합니다.
    3단계 상태 관리: 대기 → 확인완료 → 출고완료 → 전산반영

    고정 필드: 상품명, 수량, 박스수, 팔레트수, 송장번호
    커스텀 필드: PlatformColumnConfig 기반, platform_data JSON에 저장
    """

    class Platform(models.TextChoices):
        """플랫폼 선택지"""
        COUPANG = 'coupang', '쿠팡'
        KURLY = 'kurly', '컬리'
        OLIVEYOUNG = 'oliveyoung', '올리브영'
        SMARTSTORE = 'smartstore', '스마트스토어'
        OFFLINE = 'offline', '오프라인마트'
        EXPORT = 'export', '해외수출'
        OTHER = 'other', '기타'

    class Status(models.TextChoices):
        """주문 상태"""
        PENDING = 'pending', '대기'
        CONFIRMED = 'confirmed', '확인완료'
        SHIPPED = 'shipped', '출고완료'
        SYNCED = 'synced', '전산반영'

    # 기본 정보 - 거래처 + 브랜드
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        verbose_name='거래처',
        related_name='fulfillment_orders',
    )
    brand = models.ForeignKey(
        'clients.Brand',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='브랜드',
        related_name='fulfillment_orders',
    )
    platform = models.CharField(
        '플랫폼',
        max_length=20,
        choices=Platform.choices,
    )
    status = models.CharField(
        '상태',
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    # ─── 고정 필드 ───
    product_name = models.CharField(
        '상품명',
        max_length=300,
    )
    quantity = models.IntegerField(
        '수량',
        default=0,
        validators=[MinValueValidator(0)],
    )
    box_quantity = models.IntegerField(
        '박스수',
        default=0,
        validators=[MinValueValidator(0)],
    )
    pallet_quantity = models.IntegerField(
        '팔레트수',
        default=0,
        validators=[MinValueValidator(0)],
    )
    invoice_number = models.CharField(
        '송장번호',
        max_length=100,
        blank=True,
    )

    # 플랫폼별 추가 데이터 (JSON)
    platform_data = models.JSONField(
        '플랫폼별 데이터',
        default=dict,
        blank=True,
    )

    # 3단계 상태 추적 (타임스탬프 + 처리자)
    confirmed_at = models.DateTimeField(
        '확인일시',
        null=True,
        blank=True,
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='확인자',
        related_name='+',
    )
    shipped_at = models.DateTimeField(
        '출고일시',
        null=True,
        blank=True,
    )
    shipped_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='출고처리자',
        related_name='+',
    )
    synced_at = models.DateTimeField(
        '전산반영일시',
        null=True,
        blank=True,
    )
    synced_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='전산반영자',
        related_name='+',
    )

    # 시스템 정보
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='등록자',
        related_name='created_fulfillments',
    )
    created_at = models.DateTimeField('등록일시', auto_now_add=True)
    updated_at = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'fulfillment_orders'
        verbose_name = '출고 주문'
        verbose_name_plural = '출고 주문 목록'
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['client', 'platform'],
                name='idx_fulfill_client_platform',
            ),
            models.Index(
                fields=['status'],
                name='idx_fulfill_status',
            ),
        ]

    def __str__(self):
        return f"[{self.get_platform_display()}] {self.internal_code} - {self.product_name}"

    @property
    def internal_code(self):
        """자체 관리코드 (FF-00001 형식)"""
        return f"FF-{self.id:05d}"

    @property
    def status_display_class(self):
        """상태별 CSS 클래스 반환"""
        return {
            self.Status.PENDING: 'secondary',
            self.Status.CONFIRMED: 'primary',
            self.Status.SHIPPED: 'warning',
            self.Status.SYNCED: 'success',
        }.get(self.status, 'secondary')

    def can_confirm(self):
        """확인 가능 여부"""
        return self.status == self.Status.PENDING

    def can_ship(self):
        """출고 가능 여부"""
        return self.status == self.Status.CONFIRMED

    def can_sync(self):
        """전산반영 가능 여부"""
        return self.status == self.Status.SHIPPED

    def confirm(self, user):
        """확인완료 처리"""
        if not self.can_confirm():
            return False
        self.status = self.Status.CONFIRMED
        self.confirmed_at = timezone.now()
        self.confirmed_by = user
        self.save(update_fields=['status', 'confirmed_at', 'confirmed_by', 'updated_at'])
        return True

    def ship(self, user):
        """출고완료 처리"""
        if not self.can_ship():
            return False
        self.status = self.Status.SHIPPED
        self.shipped_at = timezone.now()
        self.shipped_by = user
        self.save(update_fields=['status', 'shipped_at', 'shipped_by', 'updated_at'])
        return True

    def sync(self, user):
        """전산반영 처리"""
        if not self.can_sync():
            return False
        self.status = self.Status.SYNCED
        self.synced_at = timezone.now()
        self.synced_by = user
        self.save(update_fields=['status', 'synced_at', 'synced_by', 'updated_at'])
        return True


class FulfillmentComment(models.Model):
    """
    출고 주문 댓글 모델

    발주 건별로 관리자↔고객사 간 소통을 위한 댓글 기능입니다.
    수정 요청, 확인 사항, 안내 등을 댓글로 주고받을 수 있습니다.
    """

    order = models.ForeignKey(
        FulfillmentOrder,
        on_delete=models.CASCADE,
        verbose_name='출고 주문',
        related_name='comments',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='작성자',
        related_name='fulfillment_comments',
    )
    content = models.TextField(
        '내용',
    )
    is_system = models.BooleanField(
        '시스템 메시지',
        default=False,
        help_text='상태 변경 등 시스템 자동 생성 메시지 여부',
    )
    file = models.FileField(
        '첨부파일',
        upload_to='fulfillment/comments/%Y/%m/',
        blank=True,
        default='',
        help_text='이미지(JPG, PNG, GIF, WEBP) 또는 문서(PDF, Excel, Word)',
    )
    created_at = models.DateTimeField('작성일시', auto_now_add=True)
    updated_at = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'fulfillment_comments'
        verbose_name = '출고 주문 댓글'
        verbose_name_plural = '출고 주문 댓글 목록'
        ordering = ['created_at']

    def __str__(self):
        author_name = self.author.name if self.author else '시스템'
        return f"[{self.order.internal_code}] {author_name}: {self.content[:30]}"


class PlatformColumnConfig(models.Model):
    """
    플랫폼별 커스텀 컬럼 설정

    관리자가 플랫폼별로 커스텀 컬럼을 정의합니다.
    이 설정에 따라 주문 등록 폼과 목록 테이블에 동적 컬럼이 표시됩니다.
    값은 FulfillmentOrder.platform_data JSON에 key 기준으로 저장됩니다.
    """

    class ColumnType(models.TextChoices):
        TEXT = 'text', '텍스트'
        NUMBER = 'number', '숫자'
        DATE = 'date', '날짜'

    platform = models.CharField(
        '플랫폼',
        max_length=20,
        choices=FulfillmentOrder.Platform.choices,
    )
    name = models.CharField(
        '컬럼명',
        max_length=100,
        help_text='한글 표시명 (예: 배송유형)',
    )
    key = models.CharField(
        '컬럼 키',
        max_length=100,
        help_text='내부 저장 키 (영문, 예: delivery_type)',
    )
    column_type = models.CharField(
        '타입',
        max_length=20,
        choices=ColumnType.choices,
        default=ColumnType.TEXT,
    )
    display_order = models.IntegerField(
        '표시 순서',
        default=0,
    )
    is_required = models.BooleanField(
        '필수 여부',
        default=False,
    )
    is_active = models.BooleanField(
        '활성 상태',
        default=True,
    )
    created_at = models.DateTimeField('등록일시', auto_now_add=True)
    updated_at = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'fulfillment_platform_column_configs'
        verbose_name = '플랫폼 컬럼 설정'
        verbose_name_plural = '플랫폼 컬럼 설정 목록'
        ordering = ['platform', 'display_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['platform', 'key'],
                name='uq_platform_column_key',
            ),
        ]
        indexes = [
            models.Index(
                fields=['platform', 'is_active'],
                name='idx_platform_col_active',
            ),
        ]

    def __str__(self):
        return f"[{self.get_platform_display()}] {self.name} ({self.key})"
