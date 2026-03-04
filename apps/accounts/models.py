"""
사용자 모델 모듈

커스텀 User 모델을 정의합니다.
이메일 기반 인증과 관리자 승인 기능을 포함합니다.
"""
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """
    커스텀 사용자 모델

    이메일을 기본 식별자로 사용하며, 관리자 승인이 있어야 로그인이 가능합니다.
    """

    class Role(models.TextChoices):
        """사용자 역할"""
        ADMIN = 'admin', '관리자'
        CLIENT = 'client', '거래처'
        OFFICE = 'office', '오피스팀'
        FIELD = 'field', '필드팀'
        WORKER = 'worker', '작업자'  # 하위호환 유지

    # 기본 정보
    email = models.EmailField(
        '이메일',
        unique=True,
        error_messages={
            'unique': '이미 등록된 이메일 주소입니다.',
        },
    )
    name = models.CharField('이름', max_length=100)
    phone = models.CharField('연락처', max_length=20, blank=True)

    # 역할 및 권한
    role = models.CharField(
        '역할',
        max_length=20,
        choices=Role.choices,
        default=Role.WORKER,
    )

    # 상태
    is_active = models.BooleanField(
        '활성 상태',
        default=True,
        help_text='계정 활성화 여부. 비활성화하면 로그인이 불가능합니다.',
    )
    is_staff = models.BooleanField(
        '스태프 권한',
        default=False,
        help_text='관리자 사이트 접근 권한',
    )
    is_approved = models.BooleanField(
        '승인 상태',
        default=False,
        help_text='관리자 승인 여부. 승인되지 않으면 로그인이 불가능합니다.',
    )

    # 소속 거래처 (1계정 여러 고객사 가능)
    clients = models.ManyToManyField(
        'clients.Client',
        blank=True,
        verbose_name='소속 거래처',
        related_name='users',
    )

    # 타임스탬프
    created_at = models.DateTimeField('가입일', auto_now_add=True)
    updated_at = models.DateTimeField('수정일', auto_now=True)
    last_login = models.DateTimeField('마지막 로그인', blank=True, null=True)

    # 세션 관리 (동시 로그인 방지)
    session_key = models.CharField(
        '세션 키',
        max_length=40,
        blank=True,
        null=True,
    )

    # 매니저
    objects = UserManager()

    # 인증 필드 설정
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    class Meta:
        verbose_name = '사용자'
        verbose_name_plural = '사용자'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.email})'

    def get_full_name(self):
        """전체 이름을 반환합니다."""
        return self.name

    def get_short_name(self):
        """짧은 이름을 반환합니다."""
        return self.name

    def can_login(self):
        """로그인 가능 여부를 확인합니다."""
        return self.is_active and self.is_approved

    @property
    def role_display(self):
        """역할 표시명을 반환합니다."""
        return self.get_role_display()

    @property
    def is_admin(self):
        """관리자 여부를 확인합니다."""
        return self.role == self.Role.ADMIN

    @property
    def is_client(self):
        """거래처 여부를 확인합니다."""
        return self.role == self.Role.CLIENT

    @property
    def is_office(self):
        """오피스팀 여부를 확인합니다."""
        return self.role == self.Role.OFFICE

    @property
    def is_field(self):
        """필드팀 여부를 확인합니다."""
        return self.role == self.Role.FIELD

    @property
    def is_worker(self):
        """작업자 여부를 확인합니다 (오피스팀/필드팀/기존 작업자 모두 포함)."""
        return self.role in (self.Role.WORKER, self.Role.OFFICE, self.Role.FIELD)


class WorkerProfile(models.Model):
    """
    작업자 프로필 모델

    오피스팀/필드팀/작업자의 추가 정보를 관리합니다.
    프린터 할당, PDA 기기 연결 등을 포함합니다.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='worker_profile',
        verbose_name='사용자',
    )
    assigned_printer = models.ForeignKey(
        'printing.Printer',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name='할당 프린터',
        related_name='assigned_workers',
    )
    pda_device_id = models.CharField(
        'PDA 기기 ID',
        max_length=100,
        blank=True,
        default='',
    )

    class Meta:
        verbose_name = '작업자 프로필'
        verbose_name_plural = '작업자 프로필'
        db_table = 'accounts_worker_profiles'

    def __str__(self):
        return f'{self.user.name} 프로필'


class PasswordResetCode(models.Model):
    """
    비밀번호 리셋 인증번호 모델

    이메일로 발송된 6자리 인증번호를 저장하고 유효성을 관리합니다.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='password_reset_codes',
        verbose_name='사용자',
    )
    code = models.CharField('인증번호', max_length=6)
    is_used = models.BooleanField('사용 여부', default=False)
    attempt_count = models.IntegerField('시도 횟수', default=0)
    created_at = models.DateTimeField('생성일시', auto_now_add=True)
    expires_at = models.DateTimeField('만료일시')

    class Meta:
        verbose_name = '비밀번호 리셋 인증번호'
        verbose_name_plural = '비밀번호 리셋 인증번호'
        db_table = 'accounts_password_reset_codes'
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['user', 'is_used', 'expires_at'],
                name='idx_reset_code_lookup',
            ),
        ]

    def __str__(self):
        return f'{self.user.email} - {self.code} ({"사용됨" if self.is_used else "미사용"})'

    def save(self, *args, **kwargs):
        """만료 시간 자동 설정"""
        if not self.expires_at:
            expiry_minutes = getattr(settings, 'PASSWORD_RESET_CODE_EXPIRY_MINUTES', 10)
            self.expires_at = timezone.now() + timedelta(minutes=expiry_minutes)
        super().save(*args, **kwargs)

    def is_valid(self):
        """인증번호가 유효한지 확인합니다."""
        if self.is_used:
            return False
        if timezone.now() > self.expires_at:
            return False
        if self.attempt_count >= 5:
            return False
        return True

    def mark_used(self):
        """인증번호를 사용 처리합니다."""
        self.is_used = True
        self.save(update_fields=['is_used'])

    def increment_attempt(self):
        """실패 시도 횟수를 증가시킵니다."""
        self.attempt_count += 1
        self.save(update_fields=['attempt_count'])


class SystemConfig(models.Model):
    """
    시스템 설정 모델

    키-값 기반의 글로벌 설정을 관리합니다.
    웨이브 시간, 할당 규칙, 아카이빙 기준 등 시스템 전역 설정을 저장합니다.
    """

    key = models.CharField('설정 키', max_length=100, unique=True)
    value = models.JSONField('설정 값')
    description = models.CharField('설명', max_length=200, blank=True, default='')
    updated_at = models.DateTimeField('수정일시', auto_now=True)
    updated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name='수정자',
        related_name='+',
    )

    class Meta:
        verbose_name = '시스템 설정'
        verbose_name_plural = '시스템 설정'
        db_table = 'system_configs'

    def __str__(self):
        return f'{self.key}: {self.value}'


def get_config(key, default=None):
    """시스템 설정 조회 헬퍼

    사용 예:
        from apps.accounts.models import get_config
        wave_times = get_config('wave_times', ["09:00", "15:00"])
    """
    try:
        return SystemConfig.objects.get(key=key).value
    except SystemConfig.DoesNotExist:
        return default
