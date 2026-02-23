"""
사용자 뷰 모듈

회원가입, 로그인, 사용자 관리 등의 뷰를 정의합니다.
"""
import json
import logging
import random
import secrets

from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import (
    CreateView, ListView, DetailView, UpdateView, TemplateView
)
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.password_validation import validate_password
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q

from .models import User, PasswordResetCode
from .forms import (
    UserRegistrationForm, UserLoginForm, UserApprovalForm, UserProfileForm
)
from .slack import send_signup_notification, verify_slack_signature, process_slack_action
from .email import send_password_reset_code

logger = logging.getLogger(__name__)


class RegisterView(CreateView):
    """
    회원가입 뷰

    새로운 사용자를 등록합니다.
    등록 후 관리자 승인이 필요합니다.
    """
    model = User
    form_class = UserRegistrationForm
    template_name = 'accounts/register.html'
    success_url = reverse_lazy('accounts:login')

    def dispatch(self, request, *args, **kwargs):
        """이미 로그인한 사용자는 대시보드로 리다이렉트"""
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """회원가입 성공 시 메시지 표시 및 슬랙 알림 전송"""
        response = super().form_valid(form)
        messages.success(
            self.request,
            '회원가입이 완료되었습니다. 관리자 승인 후 로그인이 가능합니다.'
        )
        # 슬랙 알림 전송 (실패해도 가입은 정상 처리)
        try:
            send_signup_notification(self.object)
        except Exception as e:
            logger.warning('슬랙 알림 전송 실패: %s', e)
        return response


class CustomLoginView(LoginView):
    """
    로그인 뷰

    승인된 사용자만 로그인이 가능합니다.
    """
    form_class = UserLoginForm
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        """로그인 성공 시 리다이렉트 URL"""
        return reverse_lazy('dashboard')

    def form_valid(self, form):
        """로그인 성공 시 메시지 표시"""
        messages.success(self.request, f'{form.get_user().name}님, 환영합니다!')
        return super().form_valid(form)


class CustomLogoutView(LogoutView):
    """로그아웃 뷰"""
    next_page = reverse_lazy('accounts:login')

    def dispatch(self, request, *args, **kwargs):
        """로그아웃 시 메시지 표시"""
        if request.user.is_authenticated:
            messages.info(request, '로그아웃되었습니다.')
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """관리자 권한 필요 믹스인"""

    def test_func(self):
        return self.request.user.is_admin or self.request.user.is_superuser

    def handle_no_permission(self):
        messages.error(self.request, '관리자 권한이 필요합니다.')
        return redirect('dashboard')


class UserListView(AdminRequiredMixin, ListView):
    """
    사용자 목록 뷰 (관리자용)

    모든 사용자 목록을 표시합니다.
    승인 대기, 승인됨, 비활성화 상태별로 필터링 가능합니다.
    """
    model = User
    template_name = 'accounts/user_list.html'
    context_object_name = 'users'
    paginate_by = 20

    def get_queryset(self):
        """필터링된 쿼리셋 반환"""
        queryset = User.objects.all()
        status = self.request.GET.get('status')

        if status == 'pending':
            queryset = queryset.filter(is_approved=False, is_active=True)
        elif status == 'approved':
            queryset = queryset.filter(is_approved=True, is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)

        # 검색
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(email__icontains=search)
            )

        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        """컨텍스트 데이터에 통계 추가"""
        context = super().get_context_data(**kwargs)
        context['pending_count'] = User.objects.filter(
            is_approved=False, is_active=True
        ).count()
        context['approved_count'] = User.objects.filter(
            is_approved=True, is_active=True
        ).count()
        context['inactive_count'] = User.objects.filter(is_active=False).count()
        context['current_status'] = self.request.GET.get('status', 'all')
        context['search_query'] = self.request.GET.get('search', '')
        return context


class UserApprovalView(AdminRequiredMixin, View):
    """
    사용자 승인 뷰 (관리자용)

    사용자를 승인하거나 거절합니다.
    """
    template_name = 'accounts/user_approval.html'

    def get(self, request, pk):
        """승인 폼 표시"""
        user = get_object_or_404(User, pk=pk)
        form = UserApprovalForm()
        return render(request, self.template_name, {
            'target_user': user,
            'form': form,
        })

    def post(self, request, pk):
        """승인/거절 처리"""
        user = get_object_or_404(User, pk=pk)
        form = UserApprovalForm(request.POST)

        if form.is_valid():
            action = form.cleaned_data['action']

            if action == 'approve':
                user.is_approved = True
                user.save()
                messages.success(
                    request,
                    f'{user.name}님의 계정이 승인되었습니다.'
                )
                # TODO: 승인 이메일 발송
            else:  # reject
                user.is_active = False
                user.save()
                messages.warning(
                    request,
                    f'{user.name}님의 계정이 거절되었습니다.'
                )
                # TODO: 거절 이메일 발송

            return redirect('accounts:user_list')

        return render(request, self.template_name, {
            'target_user': user,
            'form': form,
        })


class UserDetailView(AdminRequiredMixin, DetailView):
    """사용자 상세 뷰 (관리자용)"""
    model = User
    template_name = 'accounts/user_detail.html'
    context_object_name = 'target_user'


class UserToggleActiveView(AdminRequiredMixin, View):
    """사용자 활성화/비활성화 토글 뷰 (관리자용)"""

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)

        # 자기 자신은 비활성화 불가
        if user == request.user:
            messages.error(request, '자신의 계정은 비활성화할 수 없습니다.')
            return redirect('accounts:user_list')

        user.is_active = not user.is_active
        user.save()

        status = '활성화' if user.is_active else '비활성화'
        messages.success(request, f'{user.name}님의 계정이 {status}되었습니다.')
        return redirect('accounts:user_list')


class ProfileView(LoginRequiredMixin, UpdateView):
    """사용자 프로필 수정 뷰"""
    model = User
    form_class = UserProfileForm
    template_name = 'accounts/profile.html'
    success_url = reverse_lazy('accounts:profile')

    def get_object(self, queryset=None):
        """현재 로그인한 사용자 반환"""
        return self.request.user

    def form_valid(self, form):
        """프로필 수정 성공 시 메시지 표시"""
        messages.success(self.request, '프로필이 수정되었습니다.')
        return super().form_valid(form)


class DashboardView(LoginRequiredMixin, TemplateView):
    """
    대시보드 뷰

    사용자 역할에 따라 다른 정보를 표시합니다.
    """
    template_name = 'dashboard.html'

    def get_context_data(self, **kwargs):
        """역할별 대시보드 데이터"""
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if user.is_admin or user.is_superuser:
            # 관리자 대시보드 데이터
            context['pending_users_count'] = User.objects.filter(
                is_approved=False, is_active=True
            ).count()
            context['total_users_count'] = User.objects.filter(
                is_active=True
            ).count()
            # Phase 2 이후 추가될 데이터
            # context['total_clients_count'] = Client.objects.filter(is_active=True).count()
            # context['this_month_invoices'] = Invoice.objects.filter(...).count()

        elif user.is_client:
            # 거래처 대시보드 데이터
            # Phase 3 이후 추가될 데이터
            # context['this_month_works'] = DailyWork.objects.filter(...)
            # context['unpaid_invoices'] = Invoice.objects.filter(...)
            pass

        elif user.is_worker:
            # 작업자 대시보드 데이터
            # Phase 3 이후 추가될 데이터
            # context['today_works'] = DailyWork.objects.filter(...)
            pass

        return context


@method_decorator(csrf_exempt, name='dispatch')
class SlackInteractiveView(View):
    """
    Slack Interactive 콜백 뷰

    슬랙에서 승인/거절 버튼을 클릭하면 이 엔드포인트로 요청이 옵니다.
    Slack Signing Secret으로 요청을 검증한 뒤 처리합니다.
    """

    def post(self, request):
        # 슬랙 서명 검증
        if not verify_slack_signature(request):
            return HttpResponse('Invalid signature', status=403)

        # 슬랙은 payload를 form-encoded JSON 문자열로 전송
        try:
            payload = json.loads(request.POST.get('payload', '{}'))
        except (json.JSONDecodeError, TypeError):
            return JsonResponse({'error': 'Invalid payload'}, status=400)

        result = process_slack_action(payload)

        if result is None:
            # 링크 버튼 등 별도 응답 불필요
            return HttpResponse(status=200)

        return JsonResponse(result)


# ============================================================================
# 비밀번호 리셋 (3단계 인증번호 방식)
# ============================================================================

def _generate_reset_code():
    """6자리 숫자 인증번호를 생성합니다."""
    code_length = getattr(settings, 'PASSWORD_RESET_CODE_LENGTH', 6)
    return ''.join([str(random.randint(0, 9)) for _ in range(code_length)])


class PasswordResetRequestView(View):
    """
    비밀번호 리셋 Step 1: 이메일 입력

    이메일 주소를 입력하면 6자리 인증번호를 발송합니다.
    보안: 이메일 존재 여부와 관계없이 동일한 응답을 반환합니다.
    """
    template_name = 'accounts/password_reset_request.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        email = request.POST.get('email', '').strip().lower()

        if not email:
            messages.error(request, '이메일 주소를 입력해주세요.')
            return render(request, self.template_name)

        # 세션에 이메일 저장 (Step 2에서 사용)
        request.session['reset_email'] = email

        # 사용자 존재 여부 확인 (응답은 동일하게)
        try:
            user = User.objects.get(email=email, is_active=True)

            # 이전 미사용 코드 무효화
            PasswordResetCode.objects.filter(
                user=user, is_used=False
            ).update(is_used=True)

            # 새 인증번호 생성
            code = _generate_reset_code()
            PasswordResetCode.objects.create(user=user, code=code)

            # 이메일 발송
            try:
                send_password_reset_code(email, code)
            except Exception as e:
                logger.error('비밀번호 리셋 이메일 발송 실패: %s', e)

        except User.DoesNotExist:
            # 보안: 이메일이 존재하지 않아도 동일하게 처리
            pass

        messages.success(
            request,
            '인증번호가 이메일로 전송되었습니다. 이메일을 확인해주세요.'
        )
        return redirect('accounts:password_reset_verify')


class PasswordResetVerifyView(View):
    """
    비밀번호 리셋 Step 2: 인증번호 입력

    이메일로 받은 6자리 인증번호를 입력합니다.
    5회 초과 실패 시 인증번호가 무효화됩니다.
    """
    template_name = 'accounts/password_reset_verify.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        # 세션에 이메일이 없으면 Step 1로
        if 'reset_email' not in request.session:
            messages.warning(request, '먼저 이메일을 입력해주세요.')
            return redirect('accounts:password_reset_request')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        email = request.session.get('reset_email', '')
        expiry_minutes = getattr(settings, 'PASSWORD_RESET_CODE_EXPIRY_MINUTES', 10)
        return render(request, self.template_name, {
            'email': email,
            'expiry_minutes': expiry_minutes,
        })

    def post(self, request):
        email = request.session.get('reset_email', '')
        code_input = request.POST.get('code', '').strip()
        expiry_minutes = getattr(settings, 'PASSWORD_RESET_CODE_EXPIRY_MINUTES', 10)

        if not code_input:
            messages.error(request, '인증번호를 입력해주세요.')
            return render(request, self.template_name, {
                'email': email,
                'expiry_minutes': expiry_minutes,
            })

        try:
            user = User.objects.get(email=email, is_active=True)

            # 가장 최근 유효한 인증번호 조회
            reset_code = PasswordResetCode.objects.filter(
                user=user, is_used=False
            ).order_by('-created_at').first()

            if not reset_code or not reset_code.is_valid():
                messages.error(request, '유효한 인증번호가 없습니다. 다시 요청해주세요.')
                return redirect('accounts:password_reset_request')

            if reset_code.code != code_input:
                reset_code.increment_attempt()

                if reset_code.attempt_count >= 5:
                    reset_code.mark_used()
                    messages.error(
                        request,
                        '인증번호 입력 횟수를 초과했습니다. 다시 요청해주세요.'
                    )
                    return redirect('accounts:password_reset_request')

                remaining = 5 - reset_code.attempt_count
                messages.error(
                    request,
                    f'인증번호가 일치하지 않습니다. (남은 시도: {remaining}회)'
                )
                return render(request, self.template_name, {
                    'email': email,
                    'expiry_minutes': expiry_minutes,
                })

            # 인증 성공 → 세션에 토큰 저장
            reset_token = secrets.token_urlsafe(32)
            request.session['reset_token'] = reset_token
            request.session['reset_code_id'] = reset_code.id

            return redirect('accounts:password_reset_confirm')

        except User.DoesNotExist:
            messages.error(request, '유효한 인증번호가 없습니다. 다시 요청해주세요.')
            return redirect('accounts:password_reset_request')


class PasswordResetConfirmView(View):
    """
    비밀번호 리셋 Step 3: 새 비밀번호 설정

    인증번호 확인 후 새 비밀번호를 설정합니다.
    """
    template_name = 'accounts/password_reset_confirm.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        # 세션 토큰 확인 (Step 2를 거치지 않으면 Step 1로)
        if 'reset_token' not in request.session or 'reset_email' not in request.session:
            messages.warning(request, '비밀번호 재설정 절차를 처음부터 진행해주세요.')
            return redirect('accounts:password_reset_request')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        password1 = request.POST.get('new_password1', '')
        password2 = request.POST.get('new_password2', '')

        # 비밀번호 일치 확인
        if password1 != password2:
            messages.error(request, '비밀번호가 일치하지 않습니다.')
            return render(request, self.template_name)

        if not password1:
            messages.error(request, '비밀번호를 입력해주세요.')
            return render(request, self.template_name)

        email = request.session.get('reset_email', '')
        code_id = request.session.get('reset_code_id')

        try:
            user = User.objects.get(email=email, is_active=True)
        except User.DoesNotExist:
            messages.error(request, '사용자를 찾을 수 없습니다.')
            return redirect('accounts:password_reset_request')

        # Django 비밀번호 유효성 검사
        try:
            validate_password(password1, user)
        except ValidationError as e:
            for error in e.messages:
                messages.error(request, error)
            return render(request, self.template_name)

        # 비밀번호 변경
        user.set_password(password1)
        user.save(update_fields=['password'])

        # 인증번호 사용 처리
        if code_id:
            try:
                reset_code = PasswordResetCode.objects.get(id=code_id)
                reset_code.mark_used()
            except PasswordResetCode.DoesNotExist:
                pass

        # 세션 정리
        for key in ['reset_email', 'reset_token', 'reset_code_id']:
            request.session.pop(key, None)

        messages.success(
            request,
            '비밀번호가 성공적으로 변경되었습니다. 새 비밀번호로 로그인해주세요.'
        )
        return redirect('accounts:login')


class PasswordResetResendView(View):
    """인증번호 재발송"""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        email = request.session.get('reset_email', '')

        if not email:
            return redirect('accounts:password_reset_request')

        try:
            user = User.objects.get(email=email, is_active=True)

            # 이전 미사용 코드 무효화
            PasswordResetCode.objects.filter(
                user=user, is_used=False
            ).update(is_used=True)

            # 새 인증번호 생성
            code = _generate_reset_code()
            PasswordResetCode.objects.create(user=user, code=code)

            # 이메일 발송
            try:
                send_password_reset_code(email, code)
            except Exception as e:
                logger.error('비밀번호 리셋 이메일 재발송 실패: %s', e)

        except User.DoesNotExist:
            pass

        messages.success(request, '인증번호가 재전송되었습니다.')
        return redirect('accounts:password_reset_verify')
