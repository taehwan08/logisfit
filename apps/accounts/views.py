"""
사용자 뷰 모듈

회원가입, 로그인, 사용자 관리 등의 뷰를 정의합니다.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView, ListView, DetailView, UpdateView, TemplateView
)
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.db.models import Count, Q

from .models import User
from .forms import (
    UserRegistrationForm, UserLoginForm, UserApprovalForm, UserProfileForm
)


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
        """회원가입 성공 시 메시지 표시"""
        response = super().form_valid(form)
        messages.success(
            self.request,
            '회원가입이 완료되었습니다. 관리자 승인 후 로그인이 가능합니다.'
        )
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
