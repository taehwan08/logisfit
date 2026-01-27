"""
사용자 시리얼라이저 모듈

DRF API를 위한 시리얼라이저를 정의합니다.
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """
    사용자 시리얼라이저

    사용자 정보를 JSON으로 직렬화합니다.
    """
    role_display = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'name', 'phone',
            'role', 'role_display',
            'is_active', 'is_approved',
            'created_at', 'updated_at', 'last_login',
        ]
        read_only_fields = [
            'id', 'email', 'is_approved',
            'created_at', 'updated_at', 'last_login',
        ]


class UserListSerializer(serializers.ModelSerializer):
    """
    사용자 목록 시리얼라이저

    목록 조회에 최적화된 간소화된 정보를 제공합니다.
    """
    role_display = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'name', 'role', 'role_display',
            'is_active', 'is_approved', 'created_at',
        ]


class UserCreateSerializer(serializers.ModelSerializer):
    """
    사용자 생성 시리얼라이저

    회원가입 API에서 사용됩니다.
    """
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            'email', 'name', 'phone', 'role',
            'password', 'password_confirm',
        ]

    def validate_email(self, value):
        """이메일 중복 검사"""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('이미 등록된 이메일 주소입니다.')
        return value

    def validate(self, attrs):
        """비밀번호 일치 검사"""
        if attrs.get('password') != attrs.get('password_confirm'):
            raise serializers.ValidationError({
                'password_confirm': '비밀번호가 일치하지 않습니다.'
            })
        return attrs

    def create(self, validated_data):
        """사용자 생성"""
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')

        user = User(**validated_data)
        user.set_password(password)
        user.is_approved = False  # 관리자 승인 필요
        user.save()

        return user


class UserApprovalSerializer(serializers.Serializer):
    """
    사용자 승인 시리얼라이저

    사용자 승인/거절 API에서 사용됩니다.
    """
    action = serializers.ChoiceField(choices=['approve', 'reject'])
    reason = serializers.CharField(required=False, allow_blank=True)

    def update(self, instance, validated_data):
        """사용자 승인/거절 처리"""
        action = validated_data.get('action')

        if action == 'approve':
            instance.is_approved = True
        else:  # reject
            instance.is_active = False

        instance.save()
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    """
    비밀번호 변경 시리얼라이저
    """
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        """현재 비밀번호 확인"""
        user = self.context.get('request').user
        if not user.check_password(value):
            raise serializers.ValidationError('현재 비밀번호가 올바르지 않습니다.')
        return value

    def validate(self, attrs):
        """새 비밀번호 일치 검사"""
        if attrs.get('new_password') != attrs.get('new_password_confirm'):
            raise serializers.ValidationError({
                'new_password_confirm': '새 비밀번호가 일치하지 않습니다.'
            })
        return attrs

    def update(self, instance, validated_data):
        """비밀번호 변경"""
        instance.set_password(validated_data['new_password'])
        instance.save()
        return instance
