"""
사용자 매니저 모듈

커스텀 User 모델을 위한 매니저를 정의합니다.
이메일 기반 인증을 위해 기본 UserManager를 오버라이드합니다.
"""
from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):
    """
    커스텀 사용자 매니저

    이메일을 기본 식별자로 사용하는 사용자 모델을 위한 매니저입니다.
    """

    def create_user(self, email, password=None, **extra_fields):
        """
        일반 사용자를 생성합니다.

        Args:
            email: 사용자 이메일 (필수)
            password: 비밀번호
            **extra_fields: 추가 필드

        Returns:
            User: 생성된 사용자 인스턴스

        Raises:
            ValueError: 이메일이 제공되지 않은 경우
        """
        if not email:
            raise ValueError('이메일 주소는 필수입니다.')

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        슈퍼유저를 생성합니다.

        슈퍼유저는 자동으로 is_staff, is_superuser, is_approved가 True로 설정됩니다.

        Args:
            email: 사용자 이메일 (필수)
            password: 비밀번호
            **extra_fields: 추가 필드

        Returns:
            User: 생성된 슈퍼유저 인스턴스
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_approved', True)
        extra_fields.setdefault('role', 'admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('슈퍼유저는 is_staff=True 이어야 합니다.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('슈퍼유저는 is_superuser=True 이어야 합니다.')

        return self.create_user(email, password, **extra_fields)

    def get_pending_users(self):
        """승인 대기 중인 사용자 목록을 반환합니다."""
        return self.filter(is_approved=False, is_active=True)

    def get_approved_users(self):
        """승인된 사용자 목록을 반환합니다."""
        return self.filter(is_approved=True, is_active=True)
