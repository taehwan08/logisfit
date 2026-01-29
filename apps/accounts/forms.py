"""
사용자 폼 모듈

회원가입, 로그인, 사용자 승인 등의 폼을 정의합니다.
"""
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import authenticate

from .models import User


class UserRegistrationForm(UserCreationForm):
    """
    회원가입 폼

    이메일, 이름, 역할, 비밀번호를 입력받습니다.
    """

    email = forms.EmailField(
        label='이메일',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'example@email.com',
            'autofocus': True,
        }),
    )
    name = forms.CharField(
        label='이름',
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '홍길동',
        }),
    )
    phone = forms.CharField(
        label='연락처',
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '010-1234-5678',
        }),
    )
    role = forms.ChoiceField(
        label='역할',
        choices=[
            (User.Role.WORKER, '작업자'),
            (User.Role.CLIENT, '거래처'),
        ],
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
    )
    password1 = forms.CharField(
        label='비밀번호',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': '비밀번호 (8자 이상)',
        }),
    )
    password2 = forms.CharField(
        label='비밀번호 확인',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': '비밀번호 확인',
        }),
    )

    class Meta:
        model = User
        fields = ['email', 'name', 'phone', 'role', 'password1', 'password2']

    def clean_email(self):
        """이메일 중복 검사"""
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('이미 등록된 이메일 주소입니다.')
        return email

    def save(self, commit=True):
        """사용자 생성 (승인 대기 상태)"""
        user = super().save(commit=False)
        user.is_approved = False  # 관리자 승인 필요
        if commit:
            user.save()
        return user


class UserLoginForm(AuthenticationForm):
    """
    로그인 폼

    이메일과 비밀번호로 로그인합니다.
    승인되지 않은 사용자는 로그인이 불가능합니다.
    """

    username = forms.EmailField(
        label='이메일',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'example@email.com',
            'autofocus': True,
        }),
    )
    password = forms.CharField(
        label='비밀번호',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': '비밀번호',
        }),
    )

    error_messages = {
        'invalid_login': '이메일 또는 비밀번호가 올바르지 않습니다.',
        'inactive': '비활성화된 계정입니다.',
        'not_approved': '관리자 승인을 기다리는 중입니다. 승인 후 로그인이 가능합니다.',
    }

    def clean(self):
        """인증 및 승인 상태 확인"""
        email = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if email and password:
            # 먼저 사용자 존재 여부와 승인 상태 확인
            try:
                user = User.objects.get(email=email)
                if not user.is_approved:
                    raise forms.ValidationError(
                        self.error_messages['not_approved'],
                        code='not_approved',
                    )
                if not user.is_active:
                    raise forms.ValidationError(
                        self.error_messages['inactive'],
                        code='inactive',
                    )
            except User.DoesNotExist:
                pass  # 인증 단계에서 처리

            # 인증 시도
            self.user_cache = authenticate(
                self.request, username=email, password=password
            )
            if self.user_cache is None:
                raise forms.ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login',
                )

        return self.cleaned_data


class UserApprovalForm(forms.Form):
    """
    사용자 승인 폼

    관리자가 사용자를 승인하거나 거절할 때 사용합니다.
    """

    APPROVAL_CHOICES = [
        ('approve', '승인'),
        ('reject', '거절'),
    ]

    action = forms.ChoiceField(
        label='승인 여부',
        choices=APPROVAL_CHOICES,
        widget=forms.RadioSelect(attrs={
            'class': 'form-check-input',
        }),
    )
    reason = forms.CharField(
        label='사유 (선택)',
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': '거절 시 사유를 입력해주세요.',
        }),
    )


class UserProfileForm(forms.ModelForm):
    """
    사용자 프로필 수정 폼
    """

    class Meta:
        model = User
        fields = ['name', 'phone']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
            }),
        }
