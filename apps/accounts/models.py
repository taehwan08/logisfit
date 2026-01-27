"""
사용자 모델 모듈

커스텀 User 모델을 정의합니다.
이메일 기반 인증과 관리자 승인 기능을 포함합니다.
"""
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
        WORKER = 'worker', '작업자'

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

    # 타임스탬프
    created_at = models.DateTimeField('가입일', auto_now_add=True)
    updated_at = models.DateTimeField('수정일', auto_now=True)
    last_login = models.DateTimeField('마지막 로그인', blank=True, null=True)

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
    def is_worker(self):
        """작업자 여부를 확인합니다."""
        return self.role == self.Role.WORKER
