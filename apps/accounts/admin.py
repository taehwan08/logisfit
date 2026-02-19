"""
관리자 사이트 설정

Django 관리자 사이트에서 사용자 모델을 관리할 수 있도록 등록합니다.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """사용자 관리자 설정"""

    # 목록 표시 필드
    list_display = [
        'email', 'name', 'role', 'is_approved', 'is_active', 'created_at'
    ]

    # 목록 필터
    list_filter = ['role', 'is_approved', 'is_active', 'is_staff', 'created_at']

    # 검색 필드
    search_fields = ['email', 'name', 'phone']

    # 정렬
    ordering = ['-created_at']

    # 읽기 전용 필드
    readonly_fields = ['created_at', 'updated_at', 'last_login']

    # 상세 페이지 필드셋
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('개인 정보', {'fields': ('name', 'phone')}),
        ('권한', {
            'fields': ('role', 'is_active', 'is_approved', 'is_staff', 'is_superuser'),
        }),
        ('소속 거래처', {
            'fields': ('clients',),
        }),
        ('그룹 및 권한', {
            'fields': ('groups', 'user_permissions'),
            'classes': ('collapse',),
        }),
        ('날짜 정보', {
            'fields': ('created_at', 'updated_at', 'last_login'),
        }),
    )

    # 사용자 추가 페이지 필드셋
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email', 'name', 'phone', 'role',
                'password1', 'password2',
                'is_approved', 'is_active', 'is_staff',
            ),
        }),
    )

    # 목록에서 직접 수정 가능한 필드
    list_editable = ['is_approved', 'is_active']

    # 다대다 필드 UI
    filter_horizontal = ('clients', 'groups', 'user_permissions')

    # 목록 액션
    actions = ['approve_users', 'deactivate_users']

    @admin.action(description='선택한 사용자 승인')
    def approve_users(self, request, queryset):
        """선택한 사용자들을 승인합니다."""
        updated = queryset.update(is_approved=True)
        self.message_user(request, f'{updated}명의 사용자가 승인되었습니다.')

    @admin.action(description='선택한 사용자 비활성화')
    def deactivate_users(self, request, queryset):
        """선택한 사용자들을 비활성화합니다."""
        # 현재 로그인한 사용자는 제외
        queryset = queryset.exclude(pk=request.user.pk)
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated}명의 사용자가 비활성화되었습니다.')
