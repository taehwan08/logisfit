"""
사용자 API 뷰 모듈

DRF ViewSet을 사용한 API 엔드포인트를 정의합니다.
"""
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db import models

from .serializers import (
    UserSerializer, UserListSerializer, UserCreateSerializer,
    UserApprovalSerializer, ChangePasswordSerializer
)

User = get_user_model()


class IsAdminUser(permissions.BasePermission):
    """관리자 권한 확인"""

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            (request.user.is_admin or request.user.is_superuser)
        )


class UserViewSet(viewsets.ModelViewSet):
    """
    사용자 API ViewSet

    관리자용 사용자 CRUD 및 승인 API를 제공합니다.

    엔드포인트:
        GET /api/v1/users/ - 사용자 목록
        POST /api/v1/users/ - 사용자 생성 (회원가입)
        GET /api/v1/users/<pk>/ - 사용자 상세
        PUT /api/v1/users/<pk>/ - 사용자 수정
        DELETE /api/v1/users/<pk>/ - 사용자 삭제
        POST /api/v1/users/<pk>/approve/ - 사용자 승인/거절
        GET /api/v1/users/me/ - 현재 로그인한 사용자 정보
        POST /api/v1/users/change-password/ - 비밀번호 변경
    """
    queryset = User.objects.all().order_by('-created_at')

    def get_serializer_class(self):
        """액션에 따른 시리얼라이저 선택"""
        if self.action == 'list':
            return UserListSerializer
        elif self.action == 'create':
            return UserCreateSerializer
        elif self.action == 'approve':
            return UserApprovalSerializer
        elif self.action == 'change_password':
            return ChangePasswordSerializer
        return UserSerializer

    def get_permissions(self):
        """액션에 따른 권한 설정"""
        if self.action == 'create':
            # 회원가입은 누구나 가능
            return [permissions.AllowAny()]
        elif self.action in ['me', 'change_password']:
            # 본인 정보 조회 및 비밀번호 변경은 로그인한 사용자
            return [permissions.IsAuthenticated()]
        else:
            # 그 외는 관리자만
            return [IsAdminUser()]

    def get_queryset(self):
        """필터링된 쿼리셋 반환"""
        queryset = super().get_queryset()

        # 상태 필터
        status_filter = self.request.query_params.get('status')
        if status_filter == 'pending':
            queryset = queryset.filter(is_approved=False, is_active=True)
        elif status_filter == 'approved':
            queryset = queryset.filter(is_approved=True, is_active=True)
        elif status_filter == 'inactive':
            queryset = queryset.filter(is_active=False)

        # 역할 필터
        role = self.request.query_params.get('role')
        if role:
            queryset = queryset.filter(role=role)

        # 검색
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search) |
                models.Q(email__icontains=search)
            )

        return queryset

    def create(self, request, *args, **kwargs):
        """회원가입"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response({
            'message': '회원가입이 완료되었습니다. 관리자 승인 후 로그인이 가능합니다.',
            'user': UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """사용자 승인/거절"""
        user = self.get_object()
        serializer = self.get_serializer(user, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        action_type = request.data.get('action')
        message = '승인' if action_type == 'approve' else '거절'

        return Response({
            'message': f'{user.name}님의 계정이 {message}되었습니다.',
            'user': UserSerializer(user).data
        })

    @action(detail=False, methods=['get'])
    def me(self, request):
        """현재 로그인한 사용자 정보"""
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='change-password')
    def change_password(self, request):
        """비밀번호 변경"""
        serializer = self.get_serializer(
            request.user,
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            'message': '비밀번호가 변경되었습니다.'
        })

    @action(detail=True, methods=['post'], url_path='toggle-active')
    def toggle_active(self, request, pk=None):
        """사용자 활성화/비활성화 토글"""
        user = self.get_object()

        # 자기 자신은 비활성화 불가
        if user == request.user:
            return Response(
                {'error': '자신의 계정은 비활성화할 수 없습니다.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.is_active = not user.is_active
        user.save()

        status_text = '활성화' if user.is_active else '비활성화'
        return Response({
            'message': f'{user.name}님의 계정이 {status_text}되었습니다.',
            'user': UserSerializer(user).data
        })

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """사용자 통계"""
        return Response({
            'total': User.objects.count(),
            'pending': User.objects.filter(is_approved=False, is_active=True).count(),
            'approved': User.objects.filter(is_approved=True, is_active=True).count(),
            'inactive': User.objects.filter(is_active=False).count(),
            'by_role': {
                'admin': User.objects.filter(role='admin', is_active=True).count(),
                'client': User.objects.filter(role='client', is_active=True).count(),
                'worker': User.objects.filter(role='worker', is_active=True).count(),
            }
        })
